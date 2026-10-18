#!/usr/bin/env bash
# Lore on AWS: build, deploy and operate. Run it from anywhere:  infra/deploy.sh <command>
#
#   deploy              everything, in order (safe to re-run)
#   secrets [--from-env] [--regenerate]  fill lore/app (prompts, or reads Gemini/Slack/GitHub from .env;
#                       --regenerate makes a new session secret and FalkorDB password)
#   backend-only        rebuild the API image in CodeBuild and redeploy the app stack
#   frontend-only       rebuild the React app, upload it to S3 and clear the CloudFront cache
#   status              stacks, running task, load balancer health and the public URL
#   logs [api|falkordb] follow a container's logs (default: api)
#   exec [api|falkordb] open a shell in a running container (ECS Exec)
#   restart             start a fresh task with the same image (e.g. after changing a secret)
#   rollback <tag>      redeploy the app stack with an older image tag
#   destroy             delete EVERYTHING (asks you to type "lore")
#
# Needs: aws (v2), jq, zip, rsync, git, and for the frontend node + npm.
# Region: ap-south-1 unless AWS_REGION is set. Nothing secret is ever printed or put on a command line.
# Optional app settings for a deploy (each one changes the app stack's parameter of that name):
#   MODEL_PRO=... MODEL_FLASH=... MODEL_EMBED=... GITHUB_REPO=owner/name RATE_LIMIT_PER_MINUTE=20
set -euo pipefail
umask 077 # every file we create (temp files with secrets) is readable by this user only

REGION="${AWS_REGION:-ap-south-1}"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFN_DIR="$ROOT_DIR/infra/cfn"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

STACK_NETWORK=lore-network
STACK_REGISTRY=lore-registry
STACK_APP=lore-app
STACK_FRONTEND=lore-frontend
CLUSTER=lore
SERVICE=lore-api
BUILD_PROJECT=lore-api-build
REPO_NAME=lore-api
APP_SECRET=lore/app
ORIGIN_SECRET=lore/origin-verify
PLACEHOLDER=CHANGE_ME
# The five keys of the secret lore/app (see docs/INFRA_PLAN.md section 5).
SECRET_KEYS=(LORE_GEMINI_API_KEY LORE_SLACK_WEBHOOK_URL LORE_GITHUB_TOKEN LORE_SESSION_SECRET LORE_FALKORDB_PASSWORD)

# A private scratch folder for temp files (parameter files, the zip). Deleted when the script exits.
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# ------------------------------------------------------------------ small helpers

info() { printf '==> %s\n' "$*" >&2; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."; }

require_credentials() {
  local who
  who="$(aws sts get-caller-identity --query Arn --output text 2>/dev/null)" ||
    die "AWS credentials do not work. Check with: aws sts get-caller-identity"
  info "AWS: $who (region $REGION)"
}

account_id() { aws sts get-caller-identity --query Account --output text; }

stack_status() {
  aws cloudformation describe-stacks --stack-name "$1" --query 'Stacks[0].StackStatus' --output text 2>/dev/null ||
    echo "NOT_DEPLOYED"
}

stack_output() { # stack, output key -> value (empty if the stack or output is missing)
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue | [0]" --output text 2>/dev/null |
    sed 's/^None$//' || true
}

require_stack() { # stack, hint
  [ "$(stack_status "$1")" != "NOT_DEPLOYED" ] || die "Stack $1 does not exist yet. $2"
}

show_failures() { # print the failed events of a stack, to explain why a deploy stopped
  warn "Recent failures in $1:"
  aws cloudformation describe-stack-events --stack-name "$1" --max-items 40 \
    --query "StackEvents[?contains(ResourceStatus,'FAILED')].[LogicalResourceId,ResourceStatusReason]" \
    --output text 2>/dev/null | head -n 8 >&2 || true
}

# Deploy (create or update) one stack. Extra arguments are passed to --parameter-overrides.
cfn_deploy() { # stack, template file, [overrides...]
  local stack=$1 template=$2
  shift 2
  if [ "$(stack_status "$stack")" = "ROLLBACK_COMPLETE" ]; then
    info "$stack is in ROLLBACK_COMPLETE (a first create failed); deleting it before trying again"
    aws cloudformation delete-stack --stack-name "$stack"
    aws cloudformation wait stack-delete-complete --stack-name "$stack"
  fi
  local args=(--stack-name "$stack" --template-file "$template"
    --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset --tags project=lore)
  if [ $# -gt 0 ]; then args+=(--parameter-overrides "$@"); fi
  info "Deploying stack $stack (this waits until it is done)"
  aws cloudformation deploy "${args[@]}" || { show_failures "$stack"; die "Stack $stack failed. Details above; full log in the CloudFormation console."; }
}

validate_templates() {
  local f
  info "Validating the CloudFormation templates"
  for f in "$CFN_DIR"/*.yaml; do
    aws cloudformation validate-template --template-body "file://$f" >/dev/null ||
      die "Template $f is not valid"
  done
}

cloudfront_prefix_list_id() {
  if [ -n "${CLOUDFRONT_PREFIX_LIST_ID:-}" ]; then echo "$CLOUDFRONT_PREFIX_LIST_ID"; return; fi
  local id
  id="$(aws ec2 describe-managed-prefix-lists \
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
    --query 'PrefixLists[0].PrefixListId' --output text 2>/dev/null | sed 's/^None$//')" || true
  if [ -z "$id" ]; then
    warn "Could not look up the CloudFront prefix list; using pl-9aa247f3 (the ap-south-1 value on Oct 18 2026)"
    id=pl-9aa247f3
  fi
  echo "$id"
}

# ------------------------------------------------------------------ secrets

app_secret_json() { # prints the JSON of lore/app (a secret! only pipe it into jq)
  aws secretsmanager get-secret-value --secret-id "$APP_SECRET" --query SecretString --output text
}

# Names of the keys that are missing or still the placeholder (names only, never values).
unfilled_secret_keys() {
  local json k
  json="$(app_secret_json)" || die "Cannot read the secret $APP_SECRET. Deploy the registry stack first (infra/deploy.sh deploy)."
  for k in "${SECRET_KEYS[@]}"; do
    if ! printf '%s' "$json" | jq -e --arg k "$k" --arg p "$PLACEHOLDER" '(.[$k] // $p) != $p' >/dev/null; then
      echo "$k"
    fi
  done
}

require_secrets_filled() {
  local missing
  missing="$(unfilled_secret_keys)"
  if [ -n "$missing" ]; then
    printf 'ERROR: the secret %s still holds %s for:\n' "$APP_SECRET" "$PLACEHOLDER" >&2
    printf '  %s\n' "${missing//$'\n'/$'\n'  }" >&2
    printf 'Fill it first (the values never appear on screen or in your shell history):\n' >&2
    printf '  infra/deploy.sh secrets              # asks for the keys with hidden input\n' >&2
    printf '  infra/deploy.sh secrets --from-env   # reads Gemini, Slack and GitHub from the repo .env\n' >&2
    printf 'Then run this command again.\n' >&2
    exit 1
  fi
}

origin_verify_value() { # the X-Origin-Verify secret, generated by the registry stack
  local v
  v="$(aws secretsmanager get-secret-value --secret-id "$ORIGIN_SECRET" --query SecretString --output text |
    jq -r '.ORIGIN_VERIFY // empty')" || true
  [ -n "$v" ] || die "Cannot read $ORIGIN_SECRET. Deploy the registry stack first (infra/deploy.sh deploy)."
  printf '%s' "$v"
}

# Value of one key from the repo .env. Parses only that line (the file is never sourced) and
# prints nothing if the key is missing. Handles KEY=value, KEY="value", KEY='value' and a trailing # comment.
env_file_value() { # key
  [ -f "$ENV_FILE" ] || return 0
  local line v
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?$1=" "$ENV_FILE" | tail -n 1)" || true
  [ -n "$line" ] || return 0
  v="${line#*=}"
  v="${v#"${v%%[![:space:]]*}"}" # trim leading spaces
  case "$v" in
    \"*) v="${v#\"}"; v="${v%%\"*}" ;;
    \'*) v="${v#\'}"; v="${v%%\'*}" ;;
    *) v="${v%% \#*}"; v="${v%"${v##*[![:space:]]}"}" ;;
  esac
  printf '%s' "$v"
}

cmd_secrets() {
  local from_env=0 regenerate=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --from-env) from_env=1 ;;
      --regenerate) regenerate=1 ;;
      *) die "Unknown option '$1'. Usage: deploy.sh secrets [--from-env] [--regenerate]" ;;
    esac
    shift
  done
  need jq
  require_credentials
  local current
  current="$(app_secret_json)" || die "Cannot read $APP_SECRET. Run 'infra/deploy.sh deploy' first: it creates the registry stack that holds the secret."

  # Existing value of a key, or "" when it is missing or still the placeholder.
  existing() { printf '%s' "$current" | jq -r --arg k "$1" --arg p "$PLACEHOLDER" '(.[$k] // "") | if . == $p then "" else . end'; }

  local session fkp gemini slack github
  session="$(existing LORE_SESSION_SECRET)"
  if [ "$regenerate" = 1 ]; then session=""; fi
  if [ -z "$session" ]; then session="$(openssl rand -hex 32)"; info "Generated LORE_SESSION_SECRET"; else info "Keeping the existing LORE_SESSION_SECRET"; fi
  fkp="$(existing LORE_FALKORDB_PASSWORD)"
  if [ "$regenerate" = 1 ]; then fkp=""; fi
  if [ -z "$fkp" ]; then fkp="$(openssl rand -hex 24)"; info "Generated LORE_FALKORDB_PASSWORD"; else info "Keeping the existing LORE_FALKORDB_PASSWORD"; fi

  # For each key typed by a person: .env (with --from-env), else a hidden prompt.
  # Enter on an empty prompt keeps the stored value. Slack and GitHub may stay empty (actions are then simulated).
  ask() { # key, label, required(1/0) -> value on stdout
    local key=$1 label=$2 required=$3 value="" old
    if [ "$from_env" = 1 ]; then
      value="$(env_file_value "$key")"
      if [ -n "$value" ]; then info "$key: read from $(basename "$ENV_FILE")" >&2; printf '%s' "$value"; return; fi
      info "$key is not set in $(basename "$ENV_FILE"); asking instead" >&2
    fi
    old="$(existing "$key")"
    [ -t 0 ] || die "No terminal to ask for $key. Run this in a terminal, or use --from-env."
    local hint=""
    if [ -n "$old" ]; then hint=" [Enter keeps the stored value]"; elif [ "$required" = 0 ]; then hint=" [Enter leaves it empty: the action is simulated]"; fi
    read -rsp "$label$hint: " value
    echo >&2
    if [ -z "$value" ]; then value="$old"; fi
    if [ -z "$value" ] && [ "$required" = 1 ]; then die "$key is required."; fi
    printf '%s' "$value"
  }
  gemini="$(ask LORE_GEMINI_API_KEY "Gemini API key" 1)"
  slack="$(ask LORE_SLACK_WEBHOOK_URL "Slack incoming-webhook URL" 0)"
  github="$(ask LORE_GITHUB_TOKEN "GitHub token (issues: read & write)" 0)"
  [ -n "$gemini" ] || die "LORE_GEMINI_API_KEY is empty."

  # JSON goes through a private temp file, never through the command line (where `ps` could show it).
  local payload="$WORK_DIR/lore-app-secret.json"
  GEMINI="$gemini" SLACK="$slack" GITHUB="$github" SESSION="$session" FKP="$fkp" jq -n '{
    LORE_GEMINI_API_KEY: env.GEMINI,
    LORE_SLACK_WEBHOOK_URL: env.SLACK,
    LORE_GITHUB_TOKEN: env.GITHUB,
    LORE_SESSION_SECRET: env.SESSION,
    LORE_FALKORDB_PASSWORD: env.FKP
  }' >"$payload"
  aws secretsmanager put-secret-value --secret-id "$APP_SECRET" --secret-string "file://$payload" >/dev/null
  rm -f "$payload"
  info "Stored the five keys in $APP_SECRET."
  if [ "$(stack_status "$STACK_APP")" != "NOT_DEPLOYED" ]; then
    info "The app is already deployed: run 'infra/deploy.sh restart' so the running task picks up the new values."
  fi
}

# ------------------------------------------------------------------ backend image and app stack

image_tag() { # the git sha; a changed backend/ gets a "-dirty-<time>" suffix so the tag is always new
  local sha
  sha="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD 2>/dev/null || echo nogit)"
  if [ -n "$(git -C "$ROOT_DIR" status --porcelain -- backend 2>/dev/null)" ]; then
    echo "${sha}-dirty-$(date +%Y%m%d%H%M%S)"
  else
    echo "$sha"
  fi
}

# Zip backend/ (plus the buildspec), upload it, run CodeBuild and wait. Prints the image tag it built.
build_image() {
  need zip; need rsync; need git
  local tag bucket stage zipfile build_id status phase
  tag="$(image_tag)"
  bucket="$(stack_output "$STACK_REGISTRY" ArtifactsBucketName)"
  [ -n "$bucket" ] || die "The registry stack is missing. Run: infra/deploy.sh deploy"
  info "Packing backend/ for CodeBuild (image tag $tag)"
  stage="$WORK_DIR/stage"
  zipfile="$WORK_DIR/backend.zip"
  rm -rf "$stage" "$zipfile"
  mkdir -p "$stage"
  rsync -a \
    --exclude '.venv/' --exclude '__pycache__/' --exclude '*.py[cod]' --exclude '.pytest_cache/' \
    --exclude '.ruff_cache/' --exclude '.mypy_cache/' --exclude '*.egg-info/' --exclude 'tests/' \
    --exclude '.env' --exclude '.env.*' --exclude 'eval/report.md' --exclude 'replays/*.jsonl' \
    "$ROOT_DIR/backend/" "$stage/"
  cp "$ROOT_DIR/infra/buildspec.yml" "$stage/buildspec.yml"
  (cd "$stage" && zip -qr "$zipfile" .)
  aws s3 cp "$zipfile" "s3://$bucket/backend.zip" --only-show-errors

  info "Starting CodeBuild project $BUILD_PROJECT (about 5-8 minutes)"
  build_id="$(aws codebuild start-build --project-name "$BUILD_PROJECT" \
    --environment-variables-override "name=IMAGE_TAG,value=$tag,type=PLAINTEXT" \
    --query 'build.id' --output text)"
  while :; do
    sleep 10
    read -r status phase < <(aws codebuild batch-get-builds --ids "$build_id" \
      --query 'builds[0].[buildStatus,currentPhase]' --output text)
    info "  build $status ($phase)"
    [ "$status" = IN_PROGRESS ] || break
  done
  if [ "$status" != SUCCEEDED ]; then
    warn "Last lines of the build log:"
    aws logs tail "/aws/codebuild/$BUILD_PROJECT" --since 30m --format short 2>/dev/null | tail -n 40 >&2 || true
    die "The image build $status. Fix the error above and run: infra/deploy.sh backend-only"
  fi
  BUILT_TAG="$tag"
}

deploy_app() { # image tag
  local tag=$1 params="$WORK_DIR/app-params.json" origin_verify
  origin_verify="$(origin_verify_value)" # on its own line, so a failure here stops the script
  # The origin-verify secret and the image tag go through a temp file (the secret stays off the command line).
  ORIGIN_VERIFY="$origin_verify" IMAGE_TAG="$tag" jq -n '{Parameters: ({
      ImageTag: env.IMAGE_TAG,
      OriginVerifySecret: env.ORIGIN_VERIFY
    }
    + (if env.MODEL_PRO then {ModelPro: env.MODEL_PRO} else {} end)
    + (if env.MODEL_FLASH then {ModelFlash: env.MODEL_FLASH} else {} end)
    + (if env.MODEL_EMBED then {ModelEmbed: env.MODEL_EMBED} else {} end)
    + (if env.GITHUB_REPO then {GithubRepo: env.GITHUB_REPO} else {} end)
    + (if env.RATE_LIMIT_PER_MINUTE then {RateLimitPerMinute: env.RATE_LIMIT_PER_MINUTE} else {} end))}' >"$params"
  cfn_deploy "$STACK_APP" "$CFN_DIR/app.yaml" "file://$params"
  rm -f "$params"
  info "Waiting for the ECS service to settle"
  aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"
}

# ------------------------------------------------------------------ frontend

deploy_frontend_stack() {
  local params="$WORK_DIR/frontend-params.json" origin_verify
  origin_verify="$(origin_verify_value)"
  ORIGIN_VERIFY="$origin_verify" jq -n '{Parameters: {OriginVerifySecret: env.ORIGIN_VERIFY}}' >"$params"
  cfn_deploy "$STACK_FRONTEND" "$CFN_DIR/frontend.yaml" "file://$params"
  rm -f "$params"
}

upload_frontend() {
  need node; need npm
  local bucket dist_id url
  bucket="$(stack_output "$STACK_FRONTEND" BucketName)"
  dist_id="$(stack_output "$STACK_FRONTEND" DistributionId)"
  url="$(stack_output "$STACK_FRONTEND" PublicUrl)"
  [ -n "$bucket" ] && [ -n "$dist_id" ] || die "The frontend stack is missing. Run: infra/deploy.sh deploy"
  info "Building the React app (VITE_API_BASE is empty: the page calls /api on its own domain)"
  (cd "$ROOT_DIR/frontend" && npm ci && VITE_API_BASE='' npm run build)
  local dist="$ROOT_DIR/frontend/dist"
  info "Uploading to s3://$bucket"
  # Old files are not deleted: a visitor with an older index.html may still need the old hashed assets.
  # 1) hashed assets: cache for a year
  aws s3 sync "$dist/assets" "s3://$bucket/assets" --only-show-errors \
    --cache-control "public,max-age=31536000,immutable"
  # 2) everything else except index.html: cache for an hour
  aws s3 sync "$dist" "s3://$bucket" --only-show-errors --exclude 'assets/*' --exclude index.html \
    --cache-control "public,max-age=3600"
  # 3) index.html last, never cached, so it only points at assets that already exist
  aws s3 cp "$dist/index.html" "s3://$bucket/index.html" --only-show-errors --cache-control "no-cache"
  aws cloudfront create-invalidation --distribution-id "$dist_id" --paths /index.html --query 'Invalidation.Id' --output text >/dev/null
  info "Frontend published."
  printf '\nLore is live at: %s\n' "$url"
}

# ------------------------------------------------------------------ commands

cmd_deploy() {
  need jq; need git; need zip; need rsync; need node; need npm
  require_credentials
  validate_templates
  local prefix_list
  prefix_list="$(cloudfront_prefix_list_id)"
  info "CloudFront prefix list: $prefix_list"
  cfn_deploy "$STACK_NETWORK" "$CFN_DIR/network.yaml" "CloudFrontPrefixListId=$prefix_list"
  cfn_deploy "$STACK_REGISTRY" "$CFN_DIR/registry.yaml"
  require_secrets_filled
  build_image
  deploy_app "$BUILT_TAG"
  deploy_frontend_stack
  upload_frontend
  info "Done. Check on it any time with: infra/deploy.sh status"
}

cmd_backend_only() {
  need jq; need git
  require_credentials
  require_stack "$STACK_REGISTRY" "Run: infra/deploy.sh deploy"
  require_secrets_filled
  build_image
  deploy_app "$BUILT_TAG"
  info "Backend deployed (image $BUILT_TAG)."
}

cmd_frontend_only() {
  need jq
  require_credentials
  require_stack "$STACK_APP" "Run: infra/deploy.sh deploy"
  deploy_frontend_stack
  upload_frontend
}

cmd_status() {
  require_credentials
  local s
  printf '\nStacks\n'
  for s in "$STACK_NETWORK" "$STACK_REGISTRY" "$STACK_APP" "$STACK_FRONTEND"; do
    printf '  %-16s %s\n' "$s" "$(stack_status "$s")"
  done
  if [ "$(stack_status "$STACK_APP")" != "NOT_DEPLOYED" ]; then
    printf '\nECS service %s\n' "$SERVICE"
    aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
      --query 'services[0].{status:status,running:runningCount,desired:desiredCount,rollout:deployments[0].rolloutState,taskDefinition:taskDefinition}' \
      --output table || true
    local tasks
    tasks="$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --query 'taskArns' --output text)"
    if [ -n "$tasks" ] && [ "$tasks" != "None" ]; then
      # shellcheck disable=SC2086 # $tasks is a space-separated list of ARNs on purpose
      aws ecs describe-tasks --cluster "$CLUSTER" --tasks $tasks \
        --query 'tasks[].{task:taskArn,status:lastStatus,health:healthStatus,started:startedAt,stopped:stoppedReason}' \
        --output table || true
    else
      printf '  no running task\n'
    fi
    local tg
    tg="$(stack_output "$STACK_APP" TargetGroupArn)"
    if [ -n "$tg" ]; then
      printf '\nLoad balancer target health\n'
      aws elbv2 describe-target-health --target-group-arn "$tg" \
        --query 'TargetHealthDescriptions[].{target:Target.Id,state:TargetHealth.State,reason:TargetHealth.Reason,detail:TargetHealth.Description}' \
        --output table || true
    fi
  fi
  local url
  url="$(stack_output "$STACK_FRONTEND" PublicUrl)"
  if [ -n "$url" ]; then
    printf '\nPublic URL: %s\n' "$url"
    if command -v curl >/dev/null 2>&1; then
      printf '/api/health: '
      curl -s -m 10 "$url/api/health" || printf '(no answer)'
      printf '\n'
    fi
  fi
}

log_group_for() {
  case "${1:-api}" in
    api) echo /lore/api ;;
    falkordb) echo /lore/falkordb ;;
    *) die "Unknown container '$1'. Use api or falkordb." ;;
  esac
}

cmd_logs() {
  require_credentials
  aws logs tail "$(log_group_for "${1:-api}")" --follow --since 15m --format short
}

cmd_exec() {
  local container="${1:-api}" task shell=/bin/bash
  log_group_for "$container" >/dev/null # validates the name
  command -v session-manager-plugin >/dev/null 2>&1 ||
    die "ECS Exec needs the Session Manager plugin: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html (macOS: brew install --cask session-manager-plugin)"
  require_credentials
  [ "$container" = falkordb ] && shell=/bin/sh
  task="$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --query 'taskArns[0]' --output text)"
  { [ -n "$task" ] && [ "$task" != "None" ]; } || die "No running task. See: infra/deploy.sh status"
  aws ecs execute-command --cluster "$CLUSTER" --task "$task" --container "$container" --interactive --command "$shell"
}

cmd_restart() {
  require_credentials
  require_stack "$STACK_APP" "Run: infra/deploy.sh deploy"
  info "Starting a fresh task (the old one stops first, so expect about a minute of downtime)"
  aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --force-new-deployment --query 'service.serviceName' --output text >/dev/null
  aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"
  info "Service is stable."
}

cmd_rollback() {
  local tag="${1:-}"
  need jq
  require_credentials
  require_stack "$STACK_APP" "Run: infra/deploy.sh deploy"
  if [ -z "$tag" ]; then
    printf 'Usage: deploy.sh rollback <image-tag>\nImages in ECR (newest first):\n' >&2
    aws ecr describe-images --repository-name "$REPO_NAME" \
      --query "reverse(sort_by(imageDetails,&imagePushedAt))[].[join(', ',imageTags),imagePushedAt]" --output text >&2 || true
    exit 1
  fi
  aws ecr describe-images --repository-name "$REPO_NAME" --image-ids "imageTag=$tag" >/dev/null 2>&1 ||
    die "Image tag '$tag' is not in ECR repository $REPO_NAME. Run 'infra/deploy.sh rollback' without a tag to list them."
  deploy_app "$tag"
  info "Rolled back to image $tag."
}

empty_bucket() { # bucket name; silent if it does not exist
  if aws s3api head-bucket --bucket "$1" >/dev/null 2>&1; then
    info "Emptying bucket $1"
    aws s3 rm "s3://$1" --recursive --only-show-errors
  fi
}

empty_ecr() {
  local ids
  ids="$(aws ecr list-images --repository-name "$REPO_NAME" --query 'imageIds' --output json 2>/dev/null || echo '[]')"
  if [ "$ids" != "[]" ] && [ -n "$ids" ]; then
    info "Deleting images in ECR repository $REPO_NAME"
    aws ecr batch-delete-image --repository-name "$REPO_NAME" --image-ids "$ids" >/dev/null
  fi
}

delete_stack() {
  if [ "$(stack_status "$1")" = "NOT_DEPLOYED" ]; then return; fi
  info "Deleting stack $1 (this waits until it is gone)"
  aws cloudformation delete-stack --stack-name "$1"
  aws cloudformation wait stack-delete-complete --stack-name "$1" ||
    { show_failures "$1"; die "Could not delete $1. Fix the cause above and run destroy again."; }
}

cmd_destroy() {
  require_credentials
  local acct answer
  acct="$(account_id)"
  printf '\nThis deletes EVERYTHING Lore has in AWS account %s (%s):\n' "$acct" "$REGION"
  printf '  the website, the API, the load balancer, the FalkorDB graph on EFS (the data is lost),\n'
  printf '  the images, the build project, both secrets and the logs.\n'
  read -rp 'Type "lore" to continue: ' answer
  [ "$answer" = lore ] || die "Cancelled."
  empty_bucket "lore-web-$acct"
  delete_stack "$STACK_FRONTEND"
  delete_stack "$STACK_APP"
  empty_bucket "lore-artifacts-$acct"
  empty_ecr
  delete_stack "$STACK_REGISTRY"
  # CloudFormation leaves deleted secrets "scheduled for deletion" for 30 days, which would block the
  # name when you deploy again. Remove them for good.
  local s
  for s in "$APP_SECRET" "$ORIGIN_SECRET"; do
    aws secretsmanager delete-secret --secret-id "$s" --force-delete-without-recovery >/dev/null 2>&1 || true
  done
  delete_stack "$STACK_NETWORK"
  info "Everything is deleted."
}

usage() {
  sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

main() {
  need aws
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    deploy) cmd_deploy ;;
    secrets) cmd_secrets "$@" ;;
    backend-only) cmd_backend_only ;;
    frontend-only) cmd_frontend_only ;;
    status) cmd_status ;;
    logs) cmd_logs "$@" ;;
    exec) cmd_exec "$@" ;;
    restart) cmd_restart ;;
    rollback) cmd_rollback "$@" ;;
    destroy) cmd_destroy ;;
    help | -h | --help) usage ;;
    *) usage >&2; die "Unknown command '$cmd'." ;;
  esac
}

main "$@"

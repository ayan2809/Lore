// channel_info: does this channel exist, and is it private?
//
// Used by policy.check_post_audience before checking who can read the channel.
//
// Params: $channel (e.g. 'channel:incidents')
MATCH (ch:Channel {id: $channel})
RETURN ch.id AS id, ch.name AS name, ch.private AS private
LIMIT 1

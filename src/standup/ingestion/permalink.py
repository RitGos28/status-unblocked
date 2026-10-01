"""Native Teams permalinks, when one can honestly be built.

A Teams message deep link needs a ``19:``-form chat or channel id. A 1:1 bot
conversation reports its id in ``a:`` form, from which no per-message link can
be constructed. Rather than emit a link that does not resolve, this returns
None and a reason, which is stored in ``update.permalink_reason`` so the
absence is explained, never a silent null. The evidence view remains the
canonical citation target either way.
"""

from urllib.parse import quote


def teams_permalink(conversation_id: str, message_id: str) -> tuple[str | None, str]:
    """Return ``(url, "")`` when constructible, else ``(None, reason)``."""
    if not message_id:
        return None, "teams: activity carried no message id"
    if conversation_id.startswith("19:"):
        # Channel and group-chat ids may carry a ";messageid=..." suffix; the
        # thread id is the part before it.
        thread_id = conversation_id.split(";", 1)[0]
        return (
            f"https://teams.microsoft.com/l/message/{quote(thread_id, safe='')}/"
            f"{quote(message_id, safe='')}",
            "",
        )
    if conversation_id.startswith("a:"):
        return None, "teams 1:1 chat: conversation id is a:-form, no message deep link exists"
    return None, "teams: unrecognised conversation id form"

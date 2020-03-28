DIVIDER = {"type": "divider"}


def text(text_str):
    return {"type": "section", "text": {"type": "mrkdwn", "text": str(text_str)}}


def welcome_title(greeting_name):
    return text(f"^^^ Click to refresh\nHi {greeting_name} :wave:")


def greeting(is_ta):
    if not is_ta:
        return text("I'm here to help you find a TA during lab section.")
    else:
        return text("Please")


def active_ta(active_num):
    return text(f"{active_num} TA(s) Active:")

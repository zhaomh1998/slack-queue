DIVIDER = {"type": "divider"}


def text(text_str):
    return {"type": "section", "text": {"type": "mrkdwn", "text": str(text_str)}}


def actions(action_item_list):
    assert isinstance(action_item_list, list)
    return {"type": "actions", "elements": action_item_list}


def button(text_str, value):
    return {"type": "button",
            "text": {"type": "plain_text",
                     "text": text_str,
                     "emoji": True},
            "value": value}


def welcome_title(greeting_name):
    return text(f"Logged in as {greeting_name}")


def greeting(is_ta):
    if not is_ta:
        return text("I'm here to connect you to a TA during lab section.")
    else:
        return text("You are logged in as a TA. Remember to log off when you're done.")


def active_ta(active_num):
    return text(f"{active_num} TA(s) Active:")

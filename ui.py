import datetime
import pytz

DIVIDER = {"type": "divider"}


def text(text_str):
    if text_str == '':
        return {"type": "section", "text": {"type": "mrkdwn", "text": "\n"}}
    else:
        return {"type": "section", "text": {"type": "mrkdwn", "text": str(text_str)}}


def list_quote_text(text_str_list):
    assert isinstance(text_str_list, list)
    if len(text_str_list) == 0:
        return text('')
    else:
        return text('> ' + '\n> '.join(text_str_list))


def actions(action_item_list):
    assert isinstance(action_item_list, list)
    return {"type": "actions", "elements": action_item_list}


def button(text_str, value):
    return {"type": "button",
            "text": {"type": "plain_text",
                     "text": text_str,
                     "emoji": True},
            "value": value}


def button_styled(text_str, value, style, confirm=None):
    # style='primary': green
    # style='danger': red
    out_dict = {"type": "button",
                "text": {"type": "plain_text",
                         "text": text_str,
                         "emoji": True},
                "style": style,
                "value": value}
    if confirm is None:
        return out_dict
    else:
        out_dict["confirm"] = confirm
        return out_dict


def reset_confirm():
    return {
        "title": {"type": "plain_text",
                  "text": "Are you sure?"},
        "text": {"type": "mrkdwn",
                 "text": "This action will *clean up all* existing connections / queue / online TAs. Are you sure?"},
        "confirm": {"type": "plain_text",
                    "text": "Do it"},
        "deny": {"type": "plain_text",
                 "text": "Nevermind!"}
    }


def off_confirm():
    return {
        "title": {"type": "plain_text",
                  "text": "Are you sure?"},
        "text": {"type": "mrkdwn",
                 "text": "This action will \n• *kick and notify* all students in queue"
                         " \n• Make *all TA inactive* (_not accepting new requests_) \n"
                         "• *Lock the system* from students new request. \nProceed?"},
        "confirm": {"type": "plain_text",
                    "text": "Do it"},
        "deny": {"type": "plain_text",
                 "text": "Nevermind!"}
    }


def welcome_title(greeting_name):
    utc_now = pytz.utc.localize(datetime.datetime.utcnow())
    pst_now = utc_now.astimezone(pytz.timezone("America/Los_Angeles"))
    current_hour = pst_now.hour
    current_greeting = ("morning" if 5 <= current_hour <= 11
                        else "afternoon" if 12 <= current_hour <= 17
                        else "evening" if 18 <= current_hour <= 22
                        else "night")
    return text(f"Good {current_greeting} {greeting_name},")


def greeting(is_ta, is_active, is_system_on):
    if not is_system_on:
        return text("The queue system is off outside of lab section time."
                    " Contact a TA if you believe this is an error.")
    if not is_ta:
        return text("We are here to help! Simply click _Connect to a TA_.")
    else:
        if is_active:
            return text(":white_check_mark: Accepting requests. Remember to log off when you're done.")
        else:
            return text(":red_circle: You are currently offline. Click TA Login to start accept requests.")


def active_ta(active_num):
    return text(f"*{active_num} TA(s) Active*:")

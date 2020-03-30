from api import Slack


class TA:
    def __init__(self, slack, uid):
        assert isinstance(slack, Slack)
        self.slack = slack
        self.uid = uid
        self.active = False
        self.busy = False
        self.helping_who = 'ERR: NOT HELPING ANYONE'
        self.name = slack.get_user_name(uid)
        self.im = slack.get_im_channel(uid)

    def assign(self, student_id):
        assert not self.busy
        self.busy = True
        self.helping_who = student_id

    # FIXME: Bug: log off then you can't complete current request
    def complete(self):
        """
        Completes a TA-Student connection
        *Caller responsible for setting status for student
        **Caller responsible for whether move this TA into list of free ta according to self.active
        :return finished_student: finished student's ID
        """
        assert self.busy
        self.busy = False
        finished_student = self.helping_who
        self.helping_who = 'ERR: NOT HELPING ANYONE'
        return finished_student

    def toggle_active(self):
        self.active = not self.active
        if self.active:
            self.slack.send_chat_text(self.im, "You have started accepting requests!")
        else:
            self.slack.send_chat_text(self.im, "You are logged off and are no longer accepting new requests!")

    def get_status_text(self, ta_view):
        if self.busy:
            if ta_view:
                return f'(Busy) {self.name} currently helping {self.slack.get_user_name(self.helping_who)}'
            else:
                return f'(Busy) {self.name} currently helping a student'
        else:
            return f'{self.name}'

    def reassign(self):
        # Notify student, change student_ta_connection, change self status, etc
        raise NotImplementedError()


class QueueManager:
    """
    TA:
    - Log on
    - Log off
    - Assign
    - Complete

    Student:
    - Log on
    - Request TA
    - Exit Queue
    - Finish TA
    """

    def __init__(self, slack_web_client):
        assert isinstance(slack_web_client, Slack)
        self.free_ta = []               # List of Free TAs
        # self.busy_ta = []
        self.pairs = dict()             # Currently connected TA - Student pairs
        self.student_queue = []         # Queue for all student ids waiting for next avil TA
        self.tas = dict()               # Stores all TA instances
        self.student_status = dict()  # TODO: Refactor this into a class
        self.student_ta_connection = dict()
        self.slack = slack_web_client

    def ta_login(self, user_id):
        if user_id not in self.tas.keys():
            self.tas[user_id] = TA(self.slack, user_id)

        the_ta = self.tas[user_id]

        # TA Log on
        # A new TA added, check queue
        if not the_ta.active:
            self.free_ta.append(the_ta)
            the_ta.toggle_active()
            self.queue_move()

        # TA Log off
        else:
            if the_ta in self.free_ta:
                self.free_ta.remove(the_ta)
            # The TA complete process is responsible for removing the TA if it's already inactive (no new request)
            the_ta.toggle_active()

    def is_ta(self, user_id):
        """ Returns (is_ta, is_active) """
        if user_id in self.tas.keys():
            return True, self.tas[user_id].active
        else:
            return False, False

    def get_queue_length(self):
        return len(self.student_queue)

    def get_ta_size(self):
        return len(self.free_ta) + len(self.pairs)

    def get_queue_position(self, user_id):
        assert user_id in self.student_queue
        return self.student_queue.index(user_id) + 1

    def get_student_status(self, user_id):
        if user_id not in self.student_status.keys():
            self.student_status[user_id] = 'idle'

        return self.student_status[user_id]

    def queue_move(self):
        assert len(self.free_ta) != 0
        if len(self.student_queue) != 0:
            # Dequeue student
            user_id = self.student_queue[0]
            self.student_queue.remove(user_id)

            self.student_status[user_id] = 'busy'
            assigned_ta = self.free_ta[0]
            slack_operation = assigned_ta.assign(user_id)
            self.busy_ta.append(assigned_ta)
            self.free_ta.remove(assigned_ta)
            return slack_operation

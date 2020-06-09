import re
import datetime


class DateFoldStreamProxy:
    old_date = None
    date_re = re.compile(r"(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d).*")

    def __init__(self, stream):
        self.stream = stream

    def close(self):
        self.stream.close()

    def render_month(self, date: datetime.date):
        return f"* {date.strftime('%B %Y')}\n"

    def render_date(self, date: datetime.date):
        return f"** {date.strftime('%Y-%m-%d - %A')}\n"

    def write(self, content):
        match = self.date_re.match(content)
        if match:
            g = dict((k, int(v)) for k, v in match.groupdict().items())
            new_date = datetime.date(**g)
            old_date = self.old_date
            self.old_date = new_date

            if not old_date or new_date.month != old_date.month:
                self.stream.write(self.render_month(new_date))

            if not old_date or new_date.day != old_date.day:
                self.stream.write(self.render_date(new_date))

        # Now write the Original Content
        content = re.sub(r'\s+\n', r'\n', content, 999)
        self.stream.write(content)

"""MVC domain state; no ORM, database, accounts or privilege entities."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Problem:
    eventid: str
    name: str
    clock: int
    severity: int
    acknowledged: bool
    suppressed: bool
    recovered: bool
    tags: list
    hosts: list = field(default_factory=list)
    updates: list = field(default_factory=list)

    @classmethod
    def from_api(cls, row, host):
        return cls(str(row['eventid']), row['name'], int(row['clock']), int(row['severity']),
                   str(row.get('acknowledged', '0')) == '1',
                   str(row.get('suppressed', '0')) == '1' or bool(row.get('suppression_data')),
                   str(row.get('r_eventid', '0')) != '0', row.get('tags', []), [host], row.get('acknowledges', []))

    def age(self, now):
        return (now - self.clock) / 86400

    @property
    def started(self):
        return datetime.fromtimestamp(self.clock, timezone.utc).isoformat()


@dataclass
class Selection:
    group: dict = field(default_factory=dict)
    hosts: list = field(default_factory=list)
    problems: list = field(default_factory=list)

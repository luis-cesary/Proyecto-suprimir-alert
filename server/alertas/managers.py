"""Business service composition matching the base project's module organization."""
from services.groups import Groups
from services.hosts import Hosts
from services.problems import Problems
from services.suppression import Suppression


class AlertManager:
    def __init__(self, api, settings):
        self.groups = Groups(api)
        self.hosts = Hosts(api)
        self.problems = Problems(api, settings)
        self.suppression = Suppression(api, self.problems, settings)

import json
import time


class UsersCollection:
    def __init__(self, filename: str, ttl: int = 300) -> None:
        self.filename = filename
        self.ttl = ttl
        self.read_users()

    def read_users(self):
        with open(self.filename) as fp:
            self._members = set(json.load(fp))
        self.expire = time.time() + self.ttl

    @property
    def users(self) -> set:
        if time.time() >= self.expire:
            self.read_users()
        return self._members

    def __contains__(self, key):
        return key in self.users

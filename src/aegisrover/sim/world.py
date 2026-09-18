from dataclasses import dataclass, field
from aegisrover.core.types import Pose2, Twist2
import math

@dataclass
class Robot:
    name: str
    pose: Pose2
    twist: Twist2 = field(default_factory=lambda: Twist2(0, 0))

    def step(self, dt):
        if abs(self.twist.angular) < 1e-12:
            self.pose = Pose2(self.pose.x + self.twist.linear * dt * math.cos(self.pose.yaw), self.pose.y + self.twist.linear * dt * math.sin(self.pose.yaw), self.pose.yaw)
        else:
            w = self.twist.angular
            r = self.twist.linear / w
            theta = self.pose.yaw + w * dt
            self.pose = Pose2(self.pose.x + r * (math.sin(theta) - math.sin(self.pose.yaw)), self.pose.y - r * (math.cos(theta) - math.cos(self.pose.yaw)), theta)
        return self.pose

@dataclass
class World:
    robots: dict = field(default_factory=dict)
    time: float = 0.0

    def add(self, r):
        if r.name in self.robots:
            raise ValueError(r.name)
        self.robots[r.name] = r

    def step(self, dt):
        if dt < 0:
            raise ValueError('dt')
        self.time += dt
        return {n: r.step(dt) for n, r in self.robots.items()}

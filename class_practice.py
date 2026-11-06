from datetime import date


class Task:
    def __init__(self, name,done, due_date):
        self.name = name
        self.done = done
        self.due_date = due_date

    def complete(self):
        self.done = True

first_task = Task("和朱鸢看电影",False,"2026-11-07")
second_task =Task("和妮可吃拉面", False, "2026-11-08")

print(first_task.name)
print(first_task.done)
print(first_task.due_date)

print(second_task.name)
print(second_task.done)
print(second_task.due_date)

first_task.complete()

print(first_task.name, first_task.done, first_task.due_date)
print(second_task.name, second_task.done, second_task.due_date)

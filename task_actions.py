from datetime import date


class Task:
    def __init__(self, name, done, due_date, uid=None, version=0):
        self.name = name
        self.done = done
        self.due_date = due_date
        self.uid = uid
        self.version = version
        self.validate()

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("任务名称必须是非空文字")
        if not isinstance(self.done, bool):
            raise ValueError("任务完成状态必须是 True 或 False")
        if not isinstance(self.due_date, str):
            raise ValueError("截止日期必须是文字")
        if self.due_date != "":
            try:
                date.fromisoformat(self.due_date)
            except ValueError as error:
                raise ValueError("截止日期不是有效日期") from error

    def complete(self):
        self.done = True

    def restore(self):
        self.done = False

    def is_overdue(self):
        if self.done or self.due_date == "":
            return False
        return date.fromisoformat(self.due_date) < date.today()

    def to_dict(self):
        self.validate()
        return {
            "name": self.name,
            "done": self.done,
            "due_date": self.due_date,
        }


def show_task(number, task):
    if task.done:
        status = "已完成"
    elif task.is_overdue():
        status = "已逾期"
    else:
        status = "未完成"

    due_date = task.due_date
    if due_date == "":
        due_date = "未设置"
    print(number, status, task.name, "截止日期", due_date)


def get_task_status(task):
    return task.done

def input_due_date():
    while True:
        date_text = input("请输入截止日期，例如 2026-11-06（回车表示不设置）：").strip()
        if date_text=="":
            return ""
        try:
            due_date = date.fromisoformat(date_text)
            return due_date.isoformat()
        except ValueError:
            print("日期无效，请输入真实日期，例如 2026-11-06")

def count_completed_tasks(task_list):
    count = 0
    for task in task_list:
        if task.done:
            count += 1
    return count

def show_tasks(task_list):
    if task_list == []:
        print("暂无任务")
    else:
        for number,task in enumerate(task_list,start=1):
            show_task(number,task)

    total_count = len(task_list)
    completed_count = count_completed_tasks(task_list)
    unfinished_count = total_count - completed_count
    print("共",total_count,"条，已完成",completed_count,"条，未完成",unfinished_count)


def search_tasks(task_list):
    if task_list == []:
        print("暂无任务可搜索")
        return
    keyword = input("请输入关键词（直接回车表示不限）：").strip()
    status_choice = input("请选择状态（1 全部，2 未完成，3 已完成）：").strip()
    if status_choice not in ["1","2","3"]:
        print("无效的状态选项")
        return

    found =False

    for number,task in enumerate(task_list,start=1):
        if keyword != "" and keyword not in task.name:
            continue
        if status_choice == "2" and task.done:
            continue
        if status_choice == "3" and  not task.done:
            continue
        show_task(number,task)
        found = True
    if not found:
        print("没有符合条件的任务")

def add_task(task_list):
    task_name = input("请输入任务:")
    task_name = task_name.strip()

    if task_name == "":
        print("任务不能空")
    else:
        due_date = input_due_date()
        new_task=Task(task_name,False,due_date)
        task_list.append(new_task)
        print("已记录任务",task_name)

def get_task_index(task_list,prompt):
    number_text = input(prompt).strip()

    if number_text.isdecimal():
        try:
            task_number = int(number_text)
        except ValueError:
            print("请输入有效的数字编号")
            return None

        if 1<=task_number<=len(task_list):
            return task_number-1
        else:
            print("编号不存在")
    else:
        print("请输入有效的数字编号")
    return None

def delete_task(task_list):
    if task_list == []:
        print("暂无任务可删除")
    else:
        show_tasks(task_list)
        task_index = get_task_index(task_list,"请输入要删除的任务编号：")

        if task_index != None:
            deleted_task = task_list.pop(task_index)
            print("已删除任务",deleted_task.name)

def complete_task(task_list):
    if task_list == []:
        print("暂无任务可标记完成")
    else:
        show_tasks(task_list)
        task_index = get_task_index(task_list,"请输入要标记完成的任务编号：")

        if task_index != None:
            selected_task = task_list[task_index]

            if selected_task.done:
                print("这条任务已经完成")
            else:
                selected_task.complete()
                print("已完成任务",selected_task.name)


def restore_task(task_list):
    if task_list == []:
        print("暂无任务可恢复")
    else:
        show_tasks(task_list)
        task_index = get_task_index(task_list,"请输入要恢复为未完成的任务编号：")
        if task_index != None:
            selected_task = task_list[task_index]

            if selected_task.done:
                selected_task.restore()
                print("已恢复未完成",selected_task.name)
            else:
                print("这条任务本来就是未完成")

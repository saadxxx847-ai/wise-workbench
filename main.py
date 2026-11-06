from storage import StorageError, load_tasks, save_tasks
from task_actions import (
    add_task,
    complete_task,
    delete_task,
    get_task_status,
    restore_task,
    search_tasks,
    show_tasks,
)


def show_menu():
    print("1. 添加任务")
    print("2. 查看任务")
    print("3. 删除任务")
    print("4. 标记任务完成")
    print("5. 恢复未完成")
    print("6. 搜索和筛选任务")
    print("7. 保存并退出")


def main():
    print("欢迎使用任务管理器")
    try:
        tasks = load_tasks()
    except StorageError as error:
        print(error)
        return 1

    try:
        while True:
            tasks.sort(key=get_task_status)
            show_menu()
            choice = input("请选择：").strip()

            if choice == "1":
                add_task(tasks)
            elif choice == "2":
                show_tasks(tasks)
            elif choice == "3":
                delete_task(tasks)
            elif choice == "4":
                complete_task(tasks)
            elif choice == "5":
                restore_task(tasks)
            elif choice == "6":
                search_tasks(tasks)
            elif choice == "7":
                try:
                    save_tasks(tasks)
                except StorageError as error:
                    print(error)
                    print("保存未完成，当前任务仍保留在本次运行中。")
                else:
                    print("已保存，再见")
                    return 0
            else:
                print("无效选择")
    except (EOFError, KeyboardInterrupt):
        print("\n程序已结束，本次更改尚未保存。正常退出请使用菜单 7。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

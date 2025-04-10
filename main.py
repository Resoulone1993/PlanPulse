import flet as ft
from datetime import datetime, timedelta
import json
import os
from typing import List, Dict, Optional
import socket
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import webbrowser


class Goal:
    def __init__(self, name: str, deadline_days: int,
                 created_at: Optional[datetime] = None,
                 completed: bool = False,
                 failed: bool = False):
        self.name = name
        self.deadline_days = deadline_days
        self.created_at = created_at or datetime.now()
        self.completed = completed
        self.failed = failed

    @property
    def deadline_date(self) -> datetime:
        return self.created_at + timedelta(days=self.deadline_days)

    @property
    def days_left(self) -> int:
        return (self.deadline_date - datetime.now()).days

    def check_failed(self) -> bool:
        if not self.completed and not self.failed:
            if datetime.now() > self.deadline_date:
                self.failed = True
                return True
        return False

    def complete(self) -> None:
        if not self.failed:
            self.completed = True

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "deadline_days": self.deadline_days,
            "created_at": self.created_at.isoformat(),
            "completed": self.completed,
            "failed": self.failed
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Goal':
        return cls(
            name=data["name"],
            deadline_days=data["deadline_days"],
            created_at=datetime.fromisoformat(data["created_at"]),
            completed=data["completed"],
            failed=data["failed"]
        )


class DailyTask:
    def __init__(self, name: str, days_of_week: List[int],
                 completed_dates: Optional[List[str]] = None):
        self.name = name
        self.days_of_week = days_of_week  # 0-6 (пн-вс)
        self.completed_dates = completed_dates or []

    @property
    def is_active_today(self) -> bool:
        return datetime.now().weekday() in self.days_of_week

    @property
    def is_completed_today(self) -> bool:
        return str(datetime.now().date()) in self.completed_dates

    def complete_today(self) -> None:
        today_str = str(datetime.now().date())
        if today_str not in self.completed_dates and self.is_active_today:
            self.completed_dates.append(today_str)

    def get_active_days_names(self) -> List[str]:
        days_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        return [days_names[i] for i in self.days_of_week]

    def completion_rate(self, weeks: int = 4) -> float:
        possible_days = len(self.days_of_week) * weeks
        if possible_days == 0:
            return 0.0
        return (len(self.completed_dates) / possible_days) * 100

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "days_of_week": self.days_of_week,
            "completed_dates": self.completed_dates
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'DailyTask':
        return cls(
            name=data["name"],
            days_of_week=data["days_of_week"],
            completed_dates=data["completed_dates"]
        )


class DataManager:
    DATA_FILE = "goals_data.json"

    @classmethod
    def save_data(cls, goals: List[Goal], daily_tasks: List[DailyTask]) -> None:
        data = {
            "goals": [goal.to_dict() for goal in goals],
            "daily_tasks": [task.to_dict() for task in daily_tasks]
        }
        with open(cls.DATA_FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    def load_data(cls) -> tuple[List[Goal], List[DailyTask]]:
        if not os.path.exists(cls.DATA_FILE):
            return [], []

        with open(cls.DATA_FILE, "r") as f:
            data = json.load(f)

        goals = [Goal.from_dict(g) for g in data.get("goals", [])]
        tasks = [DailyTask.from_dict(t) for t in data.get("daily_tasks", [])]

        return goals, tasks


class GoalManager:
    def __init__(self):
        self.goals: List[Goal] = []
        self.daily_tasks: List[DailyTask] = []
        self.load_data()
        self.check_failed_goals()

    def load_data(self) -> None:
        self.goals, self.daily_tasks = DataManager.load_data()

    def save_data(self) -> None:
        DataManager.save_data(self.goals, self.daily_tasks)

    def add_goal(self, name: str, deadline_days: int) -> None:
        new_goal = Goal(name=name, deadline_days=deadline_days)
        self.goals.append(new_goal)
        self.save_data()

    def add_daily_task(self, name: str, days_of_week: List[int]) -> None:
        new_task = DailyTask(name=name, days_of_week=days_of_week)
        self.daily_tasks.append(new_task)
        self.save_data()

    def complete_goal(self, goal: Goal) -> None:
        goal.complete()
        self.save_data()

    def complete_daily_task(self, task: DailyTask) -> None:
        task.complete_today()
        self.save_data()

    def delete_goal(self, goal: Goal) -> None:
        self.goals.remove(goal)
        self.save_data()

    def delete_daily_task(self, task: DailyTask) -> None:
        self.daily_tasks.remove(task)
        self.save_data()

    def check_failed_goals(self) -> bool:
        updated = False
        for goal in self.goals:
            if goal.check_failed():
                updated = True
        if updated:
            self.save_data()
        return updated

    def get_goals_stats(self) -> Dict:
        total = len(self.goals)
        completed = len([g for g in self.goals if g.completed])
        failed = len([g for g in self.goals if g.failed])
        in_progress = total - completed - failed

        completion_rate = (completed / total * 100) if total > 0 else 0

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "completion_rate": completion_rate
        }


class WebRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, manager, *args, **kwargs):
        self.manager = manager
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Генерация HTML страницы
            html = self.generate_web_interface()
            self.wfile.write(html.encode())

        elif self.path == '/api/goals':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            goals_data = [goal.to_dict() for goal in self.manager.goals]
            self.wfile.write(json.dumps(goals_data).encode())

        elif self.path == '/api/tasks':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            tasks_data = [task.to_dict() for task in self.manager.daily_tasks]
            self.wfile.write(json.dumps(tasks_data).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def generate_web_interface(self) -> str:
        goals_html = "".join(
            f"""
            <div class="goal-card">
                <h3>{goal.name}</h3>
                <p>Срок: {goal.deadline_date.strftime('%d.%m.%Y')} ({goal.days_left} дней осталось)</p>
                <p>Статус: {"✅ Выполнено" if goal.completed else "❌ Провалено" if goal.failed else "⏳ В процессе"}</p>
                <button onclick="completeGoal('{goal.name}')" {"disabled" if goal.completed or goal.failed else ""}>
                    Отметить выполненным
                </button>
            </div>
            """ for goal in self.manager.goals
        )

        tasks_html = "".join(
            f"""
            <div class="task-card">
                <h3>{task.name}</h3>
                <p>Дни: {', '.join(task.get_active_days_names())}</p>
                <p>Статус: {"✅ Сегодня выполнено" if task.is_completed_today else "⚠️ Нужно выполнить сегодня" if task.is_active_today else "➖ Неактивно сегодня"}</p>
                <button onclick="completeTask('{task.name}')" {"disabled" if not task.is_active_today or task.is_completed_today else ""}>
                    Отметить выполненным
                </button>
            </div>
            """ for task in self.manager.daily_tasks
        )

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Менеджер целей</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                .goal-card, .task-card {{ 
                    border: 1px solid #ddd; 
                    padding: 15px; 
                    margin-bottom: 10px; 
                    border-radius: 5px; 
                }}
                button {{ 
                    background-color: #4CAF50; 
                    color: white; 
                    border: none; 
                    padding: 8px 12px; 
                    cursor: pointer; 
                    border-radius: 4px; 
                }}
                button:disabled {{ background-color: #cccccc; cursor: not-allowed; }}
                h2 {{ color: #333; }}
            </style>
        </head>
        <body>
            <h1>Менеджер целей</h1>

            <h2>Недельные цели</h2>
            <div id="goals-container">
                {goals_html}
            </div>

            <h2>Ежедневные задачи</h2>
            <div id="tasks-container">
                {tasks_html}
            </div>

            <script>
                function completeGoal(goalName) {{
                    fetch(`/api/complete_goal?name=${{encodeURIComponent(goalName)}}`, {{ method: 'POST' }})
                        .then(response => location.reload())
                        .catch(error => console.error('Error:', error));
                }}

                function completeTask(taskName) {{
                    fetch(`/api/complete_task?name=${{encodeURIComponent(taskName)}}`, {{ method: 'POST' }})
                        .then(response => location.reload())
                        .catch(error => console.error('Error:', error));
                }}

                // Автообновление каждые 30 секунд
                setTimeout(() => location.reload(), 30000);
            </script>
        </body>
        </html>
        """


class NetworkManager:
    def __init__(self, manager: GoalManager):
        self.manager = manager
        self.server = None
        self.server_thread = None
        self.local_ip = self.get_local_ip()
        self.port = 8000

    def get_local_ip(self) -> str:
        """Получает локальный IP адрес компьютера"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Не требуется реальное соединение
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def start_server(self) -> None:
        """Запускает HTTP сервер в отдельном потоке"""

        def handler(*args):
            return WebRequestHandler(self.manager, *args)

        self.server = HTTPServer((self.local_ip, self.port), handler)
        self.server_thread = Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"Сервер запущен. Откройте в браузере: http://{self.local_ip}:{self.port}")

    def stop_server(self) -> None:
        """Останавливает HTTP сервер"""
        if self.server:
            self.server.shutdown()
            self.server_thread.join()


class GoalAppUI:
    def __init__(self, page: ft.Page, manager: GoalManager):
        self.page = page
        self.manager = manager
        self.network = NetworkManager(manager)
        self.setup_page()
        self.setup_ui()
        self.start_network_server()

    def start_network_server(self):
        try:
            self.network.start_server()
            self.page.snack_bar = ft.SnackBar(
                ft.Text(f"Сервер запущен! Доступно по адресу: http://{self.network.local_ip}:{self.network.port}"))
            self.page.snack_bar.open = True
            self.page.update()
        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Ошибка запуска сервера: {str(e)}"))
            self.page.snack_bar.open = True
            self.page.update()
class GoalAppUI:
    def __init__(self, page: ft.Page, manager: GoalManager):
        self.page = page
        self.manager = manager
        self.setup_page()
        self.setup_ui()

    def setup_page(self) -> None:
        self.page.title = "Менеджер целей"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 800
        self.page.window_height = 600

    def setup_ui(self) -> None:
        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(text="Недельные цели"),
                ft.Tab(text="Ежедневные задачи"),
                ft.Tab(text="Статистика"),
            ],
            expand=True,
        )
        self.tabs.on_change = self.on_tab_change

        # Создаем содержимое вкладок
        self.weekly_goals_tab = self.create_weekly_goals_tab()
        self.daily_tasks_tab = self.create_daily_tasks_tab()
        self.stats_tab = self.create_stats_tab()

        self.page.add(self.tabs)

    def on_tab_change(self, e) -> None:
        if self.tabs.selected_index == 0:
            self.update_weekly_goals_tab()
        elif self.tabs.selected_index == 1:
            self.update_daily_tasks_tab()
        elif self.tabs.selected_index == 2:
            self.update_stats_tab()

    def create_weekly_goals_tab(self) -> ft.Column:
        self.new_goal_name = ft.TextField(label="Название цели", width=400)
        self.new_goal_deadline = ft.TextField(
            label="Срок выполнения (дней)",
            width=150,
            input_filter=ft.NumbersOnlyInputFilter()
        )

        self.goals_list = ft.ListView(expand=True)

        return ft.Column(
            controls=[
                ft.Text("Добавить новую цель на неделю", size=20, weight=ft.FontWeight.BOLD),
                ft.Row(
                    controls=[
                        self.new_goal_name,
                        self.new_goal_deadline,
                        ft.ElevatedButton(
                            "Добавить цель",
                            icon=ft.icons.ADD,
                            on_click=self.add_goal_clicked
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                ft.Divider(),
                ft.Text("Мои цели", size=20, weight=ft.FontWeight.BOLD),
                self.goals_list
            ]
        )

    def create_daily_tasks_tab(self) -> ft.Column:
        self.new_task_name = ft.TextField(label="Название задачи", width=400)

        self.day_checkboxes = [
            ft.Checkbox(label="Пн", value=False),
            ft.Checkbox(label="Вт", value=False),
            ft.Checkbox(label="Ср", value=False),
            ft.Checkbox(label="Чт", value=False),
            ft.Checkbox(label="Пт", value=False),
            ft.Checkbox(label="Сб", value=False),
            ft.Checkbox(label="Вс", value=False),
        ]

        self.tasks_list = ft.ListView(expand=True)

        return ft.Column(
            controls=[
                ft.Text("Добавить ежедневную задачу", size=20, weight=ft.FontWeight.BOLD),
                ft.Column(
                    controls=[
                        self.new_task_name,
                        ft.Row(self.day_checkboxes),
                        ft.ElevatedButton(
                            "Добавить задачу",
                            icon=ft.icons.ADD,
                            on_click=self.add_task_clicked
                        )
                    ]
                ),
                ft.Divider(),
                ft.Text("Мои ежедневные задачи", size=20, weight=ft.FontWeight.BOLD),
                self.tasks_list
            ]
        )

    def create_stats_tab(self) -> ft.Column:
        self.stats_content = ft.Column()
        return ft.Column(
            controls=[
                ft.Text("Статистика выполнения", size=20, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.stats_content
            ]
        )

    def update_weekly_goals_tab(self) -> None:
        self.goals_list.controls.clear()

        for goal in self.manager.goals:
            status_color = ft.colors.GREEN if goal.completed else (
                ft.colors.RED if goal.failed else ft.colors.BLUE
            )
            status_text = "✅ Выполнено" if goal.completed else (
                "❌ Провалено" if goal.failed else "⏳ В процессе"
            )

            goal_card = self.create_goal_card(goal, status_text, status_color)
            self.goals_list.controls.append(goal_card)

        self.page.update()

    def create_goal_card(self, goal: Goal, status_text: str, status_color: str) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            title=ft.Text(goal.name),
                            subtitle=ft.Text(
                                f"Срок: {goal.deadline_date.strftime('%d.%m.%Y')} "
                                f"({goal.days_left} дней осталось)"
                            ),
                        ),
                        ft.Row(
                            [
                                ft.Text(status_text, color=status_color),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            icon=ft.icons.CHECK,
                                            tooltip="Отметить выполненным",
                                            on_click=lambda e, g=goal: self.complete_goal_clicked(g),
                                            disabled=goal.completed or goal.failed
                                        ),
                                        ft.IconButton(
                                            icon=ft.icons.DELETE,
                                            tooltip="Удалить цель",
                                            on_click=lambda e, g=goal: self.delete_goal_clicked(g),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.END,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ]
                ),
                width=700,
                padding=10,
            )
        )

    def update_daily_tasks_tab(self) -> None:
        self.tasks_list.controls.clear()

        for task in self.manager.daily_tasks:
            task_card = self.create_task_card(task)
            self.tasks_list.controls.append(task_card)

        self.page.update()

    def create_task_card(self, task: DailyTask) -> ft.Card:
        status_text = "✅ Сегодня выполнено" if task.is_completed_today else (
            "⚠️ Нужно выполнить сегодня" if task.is_active_today else "➖ Неактивно сегодня"
        )
        status_color = ft.colors.GREEN if task.is_completed_today else (
            ft.colors.ORANGE if task.is_active_today else ft.colors.GREY
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            title=ft.Text(task.name),
                            subtitle=ft.Text(f"Дни: {', '.join(task.get_active_days_names())}"),
                        ),
                        ft.Row(
                            [
                                ft.Text(status_text, color=status_color),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            icon=ft.icons.CHECK,
                                            tooltip="Отметить выполненным сегодня",
                                            on_click=lambda e, t=task: self.complete_task_clicked(t),
                                            disabled=not task.is_active_today or task.is_completed_today
                                        ),
                                        ft.IconButton(
                                            icon=ft.icons.DELETE,
                                            tooltip="Удалить задачу",
                                            on_click=lambda e, t=task: self.delete_task_clicked(t),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.END,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ]
                ),
                width=700,
                padding=10,
            )
        )

    def update_stats_tab(self) -> None:
        self.stats_content.controls.clear()

        # Статистика по целям
        goals_stats = self.manager.get_goals_stats()
        self.stats_content.controls.append(
            ft.Column(
                [
                    ft.Text("Недельные цели", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.Text(f"Всего: {goals_stats['total']}"),
                            ft.Text(f"Выполнено: {goals_stats['completed']}", color=ft.colors.GREEN),
                            ft.Text(f"Провалено: {goals_stats['failed']}", color=ft.colors.RED),
                            ft.Text(f"В процессе: {goals_stats['in_progress']}", color=ft.colors.BLUE),
                        ],
                        spacing=20
                    ),
                    ft.ProgressBar(value=goals_stats['completion_rate'] / 100, width=700),
                    ft.Text(f"Процент выполнения: {goals_stats['completion_rate']:.1f}%"),
                    ft.Divider()
                ]
            )
        )

        # Статистика по ежедневным задачам
        if self.manager.daily_tasks:
            tasks_stats = ft.Column(
                [ft.Text("Ежедневные задачи", size=18, weight=ft.FontWeight.BOLD)]
            )

            for task in self.manager.daily_tasks:
                completion_rate = task.completion_rate()
                tasks_stats.controls.append(
                    ft.Column(
                        [
                            ft.Text(task.name, weight=ft.FontWeight.BOLD),
                            ft.Row(
                                [
                                    ft.Text(f"Выполнено раз: {len(task.completed_dates)}"),
                                    ft.Text(f"Процент выполнения: {completion_rate:.1f}%"),
                                ],
                                spacing=20
                            ),
                            ft.ProgressBar(value=completion_rate / 100, width=700),
                            ft.Divider(height=10, color=ft.colors.TRANSPARENT)
                        ]
                    )
                )

            self.stats_content.controls.append(tasks_stats)

        self.page.update()

    # Обработчики событий
    def add_goal_clicked(self, e) -> None:
        name = self.new_goal_name.value.strip()
        deadline = self.new_goal_deadline.value.strip()

        if not name or not deadline:
            self.show_snackbar("Пожалуйста, заполните все поля!")
            return

        self.manager.add_goal(name, int(deadline))
        self.new_goal_name.value = ""
        self.new_goal_deadline.value = ""
        self.update_weekly_goals_tab()
        self.show_snackbar(f"Цель '{name}' добавлена!")

    def add_task_clicked(self, e) -> None:
        name = self.new_task_name.value.strip()
        selected_days = [i for i, cb in enumerate(self.day_checkboxes) if cb.value]

        if not name or not selected_days:
            self.show_snackbar("Пожалуйста, заполните название и выберите дни!")
            return

        self.manager.add_daily_task(name, selected_days)
        self.new_task_name.value = ""
        for cb in self.day_checkboxes:
            cb.value = False
        self.update_daily_tasks_tab()
        self.show_snackbar(f"Задача '{name}' добавлена!")

    def complete_goal_clicked(self, goal: Goal) -> None:
        self.manager.complete_goal(goal)
        self.update_weekly_goals_tab()
        self.update_stats_tab()
        self.show_snackbar(f"Цель '{goal.name}' выполнена! Молодец!")

    def complete_task_clicked(self, task: DailyTask) -> None:
        self.manager.complete_daily_task(task)
        self.update_daily_tasks_tab()
        self.update_stats_tab()
        self.show_snackbar(f"Задача '{task.name}' выполнена сегодня!")

    def delete_goal_clicked(self, goal: Goal) -> None:
        self.manager.delete_goal(goal)
        self.update_weekly_goals_tab()
        self.update_stats_tab()
        self.show_snackbar(f"Цель '{goal.name}' удалена!")

    def delete_task_clicked(self, task: DailyTask) -> None:
        self.manager.delete_daily_task(task)
        self.update_daily_tasks_tab()
        self.update_stats_tab()
        self.show_snackbar(f"Задача '{task.name}' удалена!")

    def show_snackbar(self, message: str) -> None:
        self.page.snack_bar = ft.SnackBar(ft.Text(message))
        self.page.snack_bar.open = True
        self.page.update()


def main(page: ft.Page):
    manager = GoalManager()
    app_ui = GoalAppUI(page, manager)
    app_ui.update_weekly_goals_tab()  # Инициализация первой вкладки


if __name__ == "__main__":
    ft.app(target=main)
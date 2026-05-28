#!/usr/bin/env python3
"""Desktop file search app for finding regular and hidden files.

Run with:
    python3 file_search_gui.py

The script uses only the Python standard library (tkinter) and lets you
search for visible or hidden files inside a selected folder.
"""

from __future__ import annotations

import csv
import fnmatch
import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    Frame,
    LEFT,
    NORMAL,
    RIGHT,
    StringVar,
    Tk,
    filedialog,
    messagebox,
    ttk,
)

WINDOWS_HIDDEN_ATTRIBUTE = 0x02
CONTENT_SCAN_LIMIT_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class SearchResult:
    """Metadata displayed and sorted in the result table."""

    path: str
    size: int
    modified: float
    hidden: bool
    extension: str


SearchMessage = tuple[str, str | SearchResult]


@dataclass(frozen=True)
class SearchOptions:
    """User-provided settings for a search run."""

    root: Path
    pattern: str
    include_hidden: bool
    hidden_only: bool
    case_sensitive: bool
    extensions: tuple[str, ...]
    min_size: int | None
    max_size: int | None
    content_query: str


def format_size(size: int) -> str:
    """Format a byte count for display in the results table."""

    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "Б":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024

    return f"{size} Б"


def format_modified(timestamp: float) -> str:
    """Format a POSIX timestamp for display in the results table."""

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def parse_size(value: str) -> int | None:
    """Parse a user-entered size such as 500, 10KB, 2 MB, or 1.5GB."""

    text = value.strip().replace(",", ".")
    if not text:
        return None

    number = ""
    unit = ""
    for char in text:
        if char.isdigit() or char == ".":
            number += char
        elif not char.isspace():
            unit += char.lower()

    if not number:
        raise ValueError("не указано число")

    multipliers = {
        "": 1,
        "b": 1,
        "б": 1,
        "kb": 1024,
        "кб": 1024,
        "mb": 1024**2,
        "мб": 1024**2,
        "gb": 1024**3,
        "гб": 1024**3,
    }
    if unit not in multipliers:
        raise ValueError("используйте Б, КБ, МБ или ГБ")

    return int(float(number) * multipliers[unit])


def split_patterns(pattern: str) -> tuple[str, ...]:
    """Split a pattern field into one or more wildcard patterns."""

    normalized = pattern.replace(",", ";")
    parts = tuple(part.strip() for part in normalized.split(";") if part.strip())
    return parts or ("*",)


def parse_extensions(value: str) -> tuple[str, ...]:
    """Parse an extension filter field into normalized suffixes."""

    extensions: list[str] = []
    for raw_part in value.replace(",", ";").split(";"):
        part = raw_part.strip().lower()
        if not part:
            continue
        if part == "*":
            return ()
        if not part.startswith("."):
            part = f".{part}"
        extensions.append(part)
    return tuple(dict.fromkeys(extensions))


def path_is_hidden(path: Path, root: Path | None = None) -> bool:
    """Return True when a path is hidden by name or Windows attributes."""

    try:
        relative = path.relative_to(root) if root else path
    except ValueError:
        relative = path

    if any(part.startswith(".") for part in relative.parts if part not in {".", ".."}):
        return True

    try:
        attributes = path.stat().st_file_attributes  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False

    return bool(attributes & WINDOWS_HIDDEN_ATTRIBUTE)


def matches_name(filename: str, pattern: str, case_sensitive: bool) -> bool:
    """Check a file name against one or more plain-text or wildcard patterns."""

    target = filename if case_sensitive else filename.lower()
    for raw_pattern in split_patterns(pattern):
        current_pattern = raw_pattern if case_sensitive else raw_pattern.lower()
        if any(char in current_pattern for char in "*?["):
            if fnmatch.fnmatchcase(target, current_pattern):
                return True
        elif current_pattern in target:
            return True

    return False


def matches_content(path: Path, query: str, case_sensitive: bool) -> bool:
    """Search for text inside a small file without third-party dependencies."""

    if not query:
        return True

    try:
        if path.stat().st_size > CONTENT_SCAN_LIMIT_BYTES:
            return False
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

    if case_sensitive:
        return query in content
    return query.lower() in content.lower()


def result_matches_filters(path: Path, stat: os.stat_result, hidden: bool, options: SearchOptions) -> bool:
    """Apply all metadata and content filters to a candidate file."""

    if options.hidden_only and not hidden:
        return False
    if not options.include_hidden and hidden:
        return False
    if options.extensions and path.suffix.lower() not in options.extensions:
        return False
    if options.min_size is not None and stat.st_size < options.min_size:
        return False
    if options.max_size is not None and stat.st_size > options.max_size:
        return False
    return matches_content(path, options.content_query, options.case_sensitive)


def search_files(
    options: SearchOptions,
    stop_event: threading.Event,
    output: queue.Queue[SearchMessage],
) -> None:
    """Walk the selected directory and stream matching file paths to a queue."""

    found = 0
    try:
        for current_root, dirs, files in os.walk(options.root):
            if stop_event.is_set():
                output.put(("status", f"Остановлено. Найдено файлов: {found}"))
                return

            current_path = Path(current_root)
            if not options.include_hidden and not options.hidden_only:
                dirs[:] = [
                    directory
                    for directory in dirs
                    if not path_is_hidden(current_path / directory, options.root)
                ]
                if path_is_hidden(current_path, options.root):
                    continue

            output.put(("status", f"Проверяется: {current_path}"))

            for filename in files:
                if stop_event.is_set():
                    output.put(("status", f"Остановлено. Найдено файлов: {found}"))
                    return

                path = current_path / filename
                hidden = path_is_hidden(path, options.root)
                if not matches_name(filename, options.pattern, options.case_sensitive):
                    continue

                try:
                    stat = path.stat()
                except OSError:
                    continue

                if not result_matches_filters(path, stat, hidden, options):
                    continue

                found += 1
                output.put(
                    (
                        "result",
                        SearchResult(
                            path=str(path),
                            size=stat.st_size,
                            modified=stat.st_mtime,
                            hidden=hidden,
                            extension=path.suffix.lower() or "—",
                        ),
                    )
                )

        output.put(("status", f"Готово. Найдено файлов: {found}"))
    except PermissionError as exc:
        output.put(("error", f"Нет доступа: {exc}"))
    except OSError as exc:
        output.put(("error", f"Ошибка поиска: {exc}"))
    finally:
        output.put(("done", ""))


class FileSearchApp:
    """Tkinter application for searching regular and hidden files."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Hidden File Finder")
        self.root.geometry("1180x720")
        self.root.configure(bg="#16213e")

        self.search_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.output: queue.Queue[SearchMessage] = queue.Queue()
        self.result_data: dict[str, SearchResult] = {}
        self.sort_reverse: dict[str, bool] = {
            "path": False,
            "extension": False,
            "hidden": True,
            "size": True,
            "modified": True,
        }
        self.hidden_count = 0

        self.folder_var = StringVar(value=str(Path.home()))
        self.pattern_var = StringVar(value="*")
        self.extension_var = StringVar(value="")
        self.content_var = StringVar(value="")
        self.min_size_var = StringVar(value="")
        self.max_size_var = StringVar(value="")
        self.status_var = StringVar(value="Настройте фильтры и нажмите «Начать поиск».")
        self.count_var = StringVar(value="Найдено: 0 | скрытых: 0")
        self.include_hidden_var = StringVar(value="1")
        self.hidden_only_var = StringVar(value="0")
        self.case_sensitive_var = StringVar(value="0")

        self._configure_styles()
        self._build_interface()
        self.root.after(100, self._process_output)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#16213e")
        style.configure("Panel.TFrame", background="#1f4068")
        style.configure(
            "Accent.TLabel",
            background="#1f4068",
            foreground="#f8f8f2",
            font=("Arial", 10, "bold"),
        )
        style.configure(
            "Hint.TLabel",
            background="#1f4068",
            foreground="#c7d2fe",
            font=("Arial", 9),
        )
        style.configure(
            "Status.TLabel",
            background="#16213e",
            foreground="#f8f8f2",
            font=("Arial", 10),
        )
        style.configure(
            "Count.TLabel",
            background="#00adb5",
            foreground="#ffffff",
            font=("Arial", 12, "bold"),
            padding=8,
        )
        style.configure(
            "TButton",
            background="#00adb5",
            foreground="#ffffff",
            font=("Arial", 10, "bold"),
            borderwidth=0,
        )
        style.map("TButton", background=[("active", "#08d9d6"), ("disabled", "#596275")])
        style.configure(
            "Danger.TButton",
            background="#ff4d6d",
            foreground="#ffffff",
            font=("Arial", 10, "bold"),
            borderwidth=0,
        )
        style.map("Danger.TButton", background=[("active", "#ff758f"), ("disabled", "#596275")])
        style.configure("TEntry", fieldbackground="#f8f8f2", foreground="#222831")
        style.configure("TCheckbutton", background="#1f4068", foreground="#f8f8f2")
        style.map(
            "TCheckbutton",
            background=[("active", "#1f4068")],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "Treeview",
            background="#f8f8f2",
            foreground="#222831",
            fieldbackground="#f8f8f2",
            rowheight=28,
        )
        style.configure(
            "Treeview.Heading",
            background="#00adb5",
            foreground="#ffffff",
            font=("Arial", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", "#ffb703")], foreground=[("selected", "#111111")])

    def _build_interface(self) -> None:
        padding = {"padx": 10, "pady": 7}

        header = Frame(self.root, bg="#00adb5", height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Label(
            header,
            text="🕵️ Hidden File Finder — поиск спрятанных файлов",
            style="Count.TLabel",
        ).pack(side=LEFT, padx=16, pady=12)
        ttk.Label(header, textvariable=self.count_var, style="Count.TLabel").pack(side=RIGHT, padx=16, pady=12)

        controls = ttk.Frame(self.root, style="Panel.TFrame")
        controls.pack(fill="x", **padding)

        ttk.Label(controls, text="Папка:", style="Accent.TLabel").grid(row=0, column=0, sticky="w")
        folder_entry = ttk.Entry(controls, textvariable=self.folder_var)
        folder_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=6)
        ttk.Button(controls, text="Выбрать…", command=self.choose_folder).grid(row=0, column=4, sticky="ew")

        ttk.Label(controls, text="Имя/маски:", style="Accent.TLabel").grid(row=1, column=0, sticky="w")
        pattern_entry = ttk.Entry(controls, textvariable=self.pattern_var)
        pattern_entry.grid(row=1, column=1, sticky="ew", padx=6)
        pattern_entry.bind("<Return>", lambda _event: self.start_search())
        ttk.Label(controls, text="например: *;*.log;secret*", style="Hint.TLabel").grid(row=2, column=1, sticky="w", padx=6)

        ttk.Label(controls, text="Расширения:", style="Accent.TLabel").grid(row=1, column=2, sticky="w")
        extension_entry = ttk.Entry(controls, textvariable=self.extension_var)
        extension_entry.grid(row=1, column=3, sticky="ew", padx=6)
        ttk.Label(controls, text="txt;log;db или пусто", style="Hint.TLabel").grid(row=2, column=3, sticky="w", padx=6)

        ttk.Label(controls, text="Текст внутри:", style="Accent.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.content_var).grid(row=3, column=1, sticky="ew", padx=6)
        ttk.Label(controls, text="Мин. размер:", style="Accent.TLabel").grid(row=3, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.min_size_var, width=12).grid(row=3, column=3, sticky="w", padx=6)
        ttk.Label(controls, text="Макс. размер:", style="Accent.TLabel").grid(row=3, column=4, sticky="w")
        ttk.Entry(controls, textvariable=self.max_size_var, width=12).grid(row=3, column=5, sticky="w", padx=6)

        options = ttk.Frame(controls, style="Panel.TFrame")
        options.grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            options,
            text="Сканировать скрытые папки и файлы",
            variable=self.include_hidden_var,
            onvalue="1",
            offvalue="0",
        ).pack(side=LEFT)
        ttk.Checkbutton(
            options,
            text="Показывать только скрытые",
            variable=self.hidden_only_var,
            onvalue="1",
            offvalue="0",
        ).pack(side=LEFT, padx=(12, 0))
        ttk.Checkbutton(
            options,
            text="Учитывать регистр",
            variable=self.case_sensitive_var,
            onvalue="1",
            offvalue="0",
        ).pack(side=LEFT, padx=(12, 0))

        presets = ttk.Frame(controls, style="Panel.TFrame")
        presets.grid(row=5, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Button(presets, text="Режим охоты на скрытые", command=self.apply_hidden_hunt_preset).pack(side=LEFT)
        ttk.Button(presets, text="Документы", command=lambda: self.apply_extension_preset("docx;xlsx;pdf;txt;rtf")).pack(side=LEFT, padx=6)
        ttk.Button(presets, text="Архивы", command=lambda: self.apply_extension_preset("zip;rar;7z;tar;gz")).pack(side=LEFT)
        ttk.Button(presets, text="Базы/логи", command=lambda: self.apply_extension_preset("db;sqlite;log;bak")).pack(side=LEFT, padx=6)

        controls.columnconfigure(1, weight=2)
        controls.columnconfigure(3, weight=1)

        buttons = ttk.Frame(self.root, style="App.TFrame")
        buttons.pack(fill="x", **padding)
        self.start_button = ttk.Button(buttons, text="Начать поиск", command=self.start_search)
        self.start_button.pack(side=LEFT)
        self.stop_button = ttk.Button(buttons, text="Остановить", command=self.stop_search, state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=6)
        ttk.Button(buttons, text="Очистить", command=self.clear_results).pack(side=LEFT)
        ttk.Button(buttons, text="Копировать путь", command=self.copy_selected_paths).pack(side=LEFT, padx=6)
        ttk.Button(buttons, text="Экспорт CSV", command=self.export_results).pack(side=LEFT)
        ttk.Button(
            buttons,
            text="Удалить выбранные",
            command=self.delete_selected_files,
            style="Danger.TButton",
        ).pack(side=LEFT, padx=6)
        ttk.Button(buttons, text="Открыть папку результата", command=self.open_selected_parent).pack(side=RIGHT)

        results_frame = ttk.Frame(self.root, style="App.TFrame")
        results_frame.pack(fill=BOTH, expand=True, **padding)

        self.results = ttk.Treeview(
            results_frame,
            columns=("path", "extension", "hidden", "size", "modified"),
            show="headings",
            selectmode="extended",
        )
        self.results.heading("path", text="Файл", command=lambda: self.sort_results("path"))
        self.results.heading("extension", text="Тип", command=lambda: self.sort_results("extension"))
        self.results.heading("hidden", text="Скрыт", command=lambda: self.sort_results("hidden"))
        self.results.heading("size", text="Размер", command=lambda: self.sort_results("size"))
        self.results.heading("modified", text="Дата изменения", command=lambda: self.sort_results("modified"))
        self.results.column("path", width=620, anchor="w")
        self.results.column("extension", width=90, anchor="center")
        self.results.column("hidden", width=90, anchor="center")
        self.results.column("size", width=120, anchor="e")
        self.results.column("modified", width=180, anchor="center")
        self.results.bind("<Double-1>", self.open_selected_file)
        self.results.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results.yview)
        scrollbar.pack(side=RIGHT, fill="y")
        self.results.configure(yscrollcommand=scrollbar.set)
        self.results.tag_configure("odd", background="#e3fdfd")
        self.results.tag_configure("even", background="#f8f8f2")
        self.results.tag_configure("hidden", background="#ffe5ec")

        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", style="Status.TLabel")
        status.pack(fill="x", **padding)

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if folder:
            self.folder_var.set(folder)

    def apply_hidden_hunt_preset(self) -> None:
        self.pattern_var.set("*")
        self.extension_var.set("")
        self.content_var.set("")
        self.min_size_var.set("")
        self.max_size_var.set("")
        self.include_hidden_var.set("1")
        self.hidden_only_var.set("1")
        self.status_var.set("Включён режим поиска только скрытых файлов.")

    def apply_extension_preset(self, extensions: str) -> None:
        self.extension_var.set(extensions)
        self.pattern_var.set("*")
        self.status_var.set(f"Фильтр расширений: {extensions}")

    def clear_results(self) -> None:
        for item in self.results.get_children():
            self.results.delete(item)
        self.result_data.clear()
        self.hidden_count = 0
        self.count_var.set("Найдено: 0 | скрытых: 0")
        self.status_var.set("Список результатов очищен.")

    def build_search_options(self) -> SearchOptions | None:
        folder = Path(self.folder_var.get()).expanduser()
        pattern = self.pattern_var.get().strip() or "*"

        if not folder.is_dir():
            messagebox.showerror("Неверная папка", "Укажите существующую папку для поиска.")
            return None

        try:
            min_size = parse_size(self.min_size_var.get())
            max_size = parse_size(self.max_size_var.get())
        except ValueError as exc:
            messagebox.showerror("Неверный размер", str(exc))
            return None

        if min_size is not None and max_size is not None and min_size > max_size:
            messagebox.showerror("Неверный размер", "Минимальный размер больше максимального.")
            return None

        try:
            extensions = parse_extensions(self.extension_var.get())
        except ValueError as exc:
            messagebox.showerror("Неверные расширения", str(exc))
            return None

        return SearchOptions(
            root=folder,
            pattern=pattern,
            include_hidden=self.include_hidden_var.get() == "1",
            hidden_only=self.hidden_only_var.get() == "1",
            case_sensitive=self.case_sensitive_var.get() == "1",
            extensions=extensions,
            min_size=min_size,
            max_size=max_size,
            content_query=self.content_var.get().strip(),
        )

    def start_search(self) -> None:
        if self.search_thread and self.search_thread.is_alive():
            messagebox.showinfo("Поиск уже запущен", "Дождитесь завершения или нажмите «Остановить».")
            return

        options = self.build_search_options()
        if options is None:
            return

        self.clear_results()
        self.stop_event.clear()
        self.start_button.configure(state=DISABLED)
        self.stop_button.configure(state=NORMAL)
        self.status_var.set("Поиск запущен…")

        self.search_thread = threading.Thread(
            target=search_files,
            args=(options, self.stop_event, self.output),
            daemon=True,
        )
        self.search_thread.start()

    def stop_search(self) -> None:
        self.stop_event.set()
        self.status_var.set("Останавливаю поиск…")

    def open_path(self, path: Path) -> None:
        """Open a file or folder with the operating system default application."""

        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Не удалось открыть", str(exc))

    def selected_paths(self) -> list[Path]:
        return [Path(self.results.item(item, "values")[0]) for item in self.results.selection()]

    def open_selected_file(self, _event: object | None = None) -> None:
        paths = self.selected_paths()
        if not paths:
            return

        path = paths[0]
        if not path.exists():
            messagebox.showerror("Файл не найден", f"Файл не существует: {path}")
            return

        self.open_path(path)

    def open_selected_parent(self) -> None:
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo("Нет выбора", "Выберите найденный файл в списке.")
            return

        parent = paths[0].parent
        if not parent.exists():
            messagebox.showerror("Папка не найдена", f"Папка не существует: {parent}")
            return

        self.open_path(parent)

    def copy_selected_paths(self) -> None:
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo("Нет выбора", "Выберите один или несколько файлов в списке.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(str(path) for path in paths))
        self.status_var.set(f"Скопировано путей: {len(paths)}")

    def export_results(self) -> None:
        if not self.result_data:
            messagebox.showinfo("Нет результатов", "Сначала выполните поиск.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=(("CSV", "*.csv"), ("Все файлы", "*.*")),
            initialfile="hidden_file_finder_results.csv",
        )
        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["path", "extension", "hidden", "size_bytes", "modified"])
                for item in self.results.get_children():
                    result = self.result_data[item]
                    writer.writerow(
                        [
                            result.path,
                            result.extension,
                            "yes" if result.hidden else "no",
                            result.size,
                            format_modified(result.modified),
                        ]
                    )
        except OSError as exc:
            messagebox.showerror("Не удалось экспортировать", str(exc))
            return

        self.status_var.set(f"Экспортировано результатов: {len(self.result_data)}")

    def delete_selected_files(self) -> None:
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Нет выбора", "Выберите один или несколько файлов в списке.")
            return

        paths = self.selected_paths()
        confirmed = messagebox.askyesno(
            "Подтвердите удаление",
            f"Удалить выбранные файлы безвозвратно? Количество: {len(paths)}",
        )
        if not confirmed:
            return

        deleted = 0
        errors: list[str] = []
        for item, path in zip(selected, paths):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue

            result = self.result_data.pop(item, None)
            if result and result.hidden:
                self.hidden_count -= 1
            self.results.delete(item)
            deleted += 1

        self.update_count_label()
        self.status_var.set(f"Удалено файлов: {deleted}")
        if errors:
            messagebox.showwarning("Не все файлы удалены", "\n".join(errors[:10]))

    def sort_results(self, column: str) -> None:
        reverse = self.sort_reverse[column]

        def sort_key(item: str) -> str | int | float | bool:
            result = self.result_data[item]
            if column == "size":
                return result.size
            if column == "modified":
                return result.modified
            if column == "hidden":
                return result.hidden
            if column == "extension":
                return result.extension
            return result.path.lower()

        items = sorted(self.results.get_children(), key=sort_key, reverse=reverse)
        for index, item in enumerate(items):
            self.results.move(item, "", index)
            result = self.result_data[item]
            self.results.item(item, tags=self.row_tags(index, result.hidden))

        self.sort_reverse[column] = not reverse
        direction = "по убыванию" if reverse else "по возрастанию"
        labels = {
            "path": "имени",
            "extension": "типу",
            "hidden": "скрытым файлам",
            "size": "размеру",
            "modified": "дате изменения",
        }
        self.status_var.set(f"Результаты отсортированы по {labels[column]} {direction}.")

    def row_tags(self, index: int, hidden: bool) -> tuple[str, ...]:
        if hidden:
            return ("hidden",)
        return ("even" if index % 2 == 0 else "odd",)

    def update_count_label(self) -> None:
        self.count_var.set(f"Найдено: {len(self.result_data)} | скрытых: {self.hidden_count}")

    def _process_output(self) -> None:
        while True:
            try:
                kind, value = self.output.get_nowait()
            except queue.Empty:
                break

            if kind == "result":
                if not isinstance(value, SearchResult):
                    continue
                result_count = len(self.results.get_children())
                item = self.results.insert(
                    "",
                    END,
                    values=(
                        value.path,
                        value.extension,
                        "да" if value.hidden else "нет",
                        format_size(value.size),
                        format_modified(value.modified),
                    ),
                    tags=self.row_tags(result_count, value.hidden),
                )
                self.result_data[item] = value
                if value.hidden:
                    self.hidden_count += 1
                self.update_count_label()
            elif kind == "status" and isinstance(value, str):
                self.status_var.set(value)
            elif kind == "error" and isinstance(value, str):
                self.status_var.set(value)
                messagebox.showwarning("Предупреждение", value)
            elif kind == "done":
                self.start_button.configure(state=NORMAL)
                self.stop_button.configure(state=DISABLED)

        self.root.after(100, self._process_output)


def main() -> None:
    root = Tk()
    FileSearchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

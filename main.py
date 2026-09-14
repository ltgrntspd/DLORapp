import os
import flet as ft
import database as db


def main(page: ft.Page):
    page.title = "Учёт работы ЛОР-врача"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 450
    page.window.height = 800

    # --- Единый сервис для отправки/сохранения файлов ---
    def export_and_share(file_path: str):
        abs_path = os.path.abspath(file_path)
        
        if not os.path.exists(abs_path):
            snack = ft.SnackBar(ft.Text("Ошибка: файл не найден"))
            page.overlay.append(snack)
            snack.open = True
            page.update()
            return

        # Проверяем наличие метода share (для Android/iOS)
        if hasattr(page, "share"):
            try:
                page.share(files=[abs_path])
                snack = ft.SnackBar(ft.Text("Выберите приложение для отправки"))
            except Exception:
                snack = ft.SnackBar(ft.Text(f"Сохранено: {abs_path}"))
        else:
            # На Windows/Linux откроет файл стандартной программой
            try:
                os.startfile(abs_path)
                snack = ft.SnackBar(ft.Text(f"Файл открыт: {abs_path}"))
            except Exception:
                snack = ft.SnackBar(ft.Text(f"Сохранено локально: {abs_path}"))

        page.overlay.append(snack)
        snack.open = True
        page.update()

    def get_room_names():
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            return {row["key"]: row["value"] for row in cursor.fetchall()}

    room_names = db.get_room_names()

# --- Диалог просмотра/редактирования пациента ---
    def open_patient_details_dialog(patient: dict):
        rooms = db.get_room_names()

        room_dropdown = ft.Dropdown(
            label="Палата / Локация",
            options=[ft.dropdown.Option(k, v) for k, v in rooms.items()],
            value=patient["room_key"],
        )

        diag_planned_in = ft.TextField(
            label="Планируемый диагноз", value=patient["diagnosis_planned"] or ""
        )
        op_planned_in = ft.TextField(
            label="Планируемая операция", value=patient["operation_planned"] or ""
        )

        # Оперирован ли
        is_op_check = ft.Checkbox(
            label="Пациент прооперирован", value=bool(patient["is_operated"])
        )

        op_done_in = ft.TextField(
            label="Выполненная операция",
            value=patient["operation_done"] or patient["operation_planned"] or "",
            visible=bool(patient["is_operated"]),
        )
        intraop_in = ft.TextField(
            label="Интраоперационные осложнения",
            value=patient["intraop_complications"] or "",
            visible=bool(patient["is_operated"]),
        )
        postop_in = ft.TextField(
            label="Особенности послеоперационного периода",
            value=patient["postop_features"] or "",
            visible=bool(patient["is_operated"]),
        )

        def toggle_operated_fields(e):
            is_visible = is_op_check.value
            op_done_in.visible = is_visible
            intraop_in.visible = is_visible
            postop_in.visible = is_visible
            page.update()

        is_op_check.on_change = toggle_operated_fields

        # --- Логика списка задач с чекбоксами ---
        raw_tasks = [
            t.strip()
            for t in (patient["tasks"] or "").split("\n")
            if t.strip()
        ]
        
        # Список активных задач (хранит словари {'text': str, 'checkbox': Checkbox})
        task_items = []
        tasks_column = ft.Column(spacing=2)

        def make_task_checkbox(task_text):
            cb = ft.Checkbox(label=task_text, value=False)
            
            def on_cb_change(e):
                if cb.value:
                    cb.label_style = ft.TextStyle(
                        decoration=ft.TextDecoration.LINE_THROUGH,
                        color=ft.Colors.GREY_500,
                    )
                else:
                    cb.label_style = ft.TextStyle(
                        decoration=ft.TextDecoration.NONE,
                        color=ft.Colors.BLACK,
                    )
                page.update()

            cb.on_change = on_cb_change
            return cb

        for t_text in raw_tasks:
            cb_control = make_task_checkbox(t_text)
            task_items.append({"text": t_text, "checkbox": cb_control})
            tasks_column.controls.append(cb_control)

        new_task_in = ft.TextField(
            label="Добавить новую задачу",
            hint_text="Например: Взять мазок, проверить анализы...",
        )

        def close_dlg(e=None):
            details_dialog.open = False
            page.update()

        def save_changes(e):
            # Собираем только НЕ отмеченные галочкой (невыполненные) задачи
            remaining_tasks = [
                item["text"]
                for item in task_items
                if not item["checkbox"].value
            ]
            
            # Если ввели новую задачу — добавляем ее в список
            if new_task_in.value and new_task_in.value.strip():
                remaining_tasks.append(new_task_in.value.strip())

            # Объединяем обратно в одну строку через перенос строки для БД
            final_tasks_str = "\n".join(remaining_tasks)

            db.update_patient_details(
                p_id=patient["id"],
                room_key=room_dropdown.value,
                diagnosis_planned=diag_planned_in.value or "",
                operation_planned=op_planned_in.value or "",
                is_operated=1 if is_op_check.value else 0,
                operation_done=op_done_in.value or "",
                intraop_complications=intraop_in.value or "",
                postop_features=postop_in.value or "",
                tasks=final_tasks_str,
            )
            details_dialog.open = False
            refresh_hospital_view()

        def process_discharge(e):
            stage = patient["discharge_stage"]
            db.advance_discharge_stage(patient["id"], stage)
            details_dialog.open = False
            refresh_hospital_view()

            msg = "Пациент выписан!" if stage == 0 else "Пациент отправлен в архив!"
            snack = ft.SnackBar(ft.Text(msg))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        discharge_btn_text = (
            "Выписать пациента (Шаг 1)"
            if patient["discharge_stage"] == 0
            else "Отправить в архив (Шаг 2)"
        )

        details_dialog = ft.AlertDialog(
            title=ft.Text(f"Карточка: {patient['fio']}"),
            content=ft.Column(
                [
                    room_dropdown,
                    diag_planned_in,
                    op_planned_in,
                    is_op_check,
                    op_done_in,
                    intraop_in,
                    postop_in,
                    ft.Text("Текущие задачи:", weight=ft.FontWeight.BOLD, size=13),
                    tasks_column if raw_tasks else ft.Text("Нет задач", italic=True, color=ft.Colors.GREY_500),
                    new_task_in,
                    ft.Divider(),
                    ft.Button(
                        discharge_btn_text,
                        icon=ft.Icons.LOGOUT,
                        icon_color=ft.Colors.RED_600,
                        on_click=process_discharge,
                    ),
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dlg),
                ft.Button("Сохранить", on_click=save_changes),
            ],
        )

        page.overlay.append(details_dialog)
        details_dialog.open = True
        page.update()

    # --- Диалог добавления пациента ---
    def open_add_patient_dialog(e):
        rooms = db.get_room_names()

        fio_field = ft.TextField(
            label="ФИО пациента",
            hint_text="Например: Иванов Иван Иванович",
            autofocus=True,
        )
        dob_field = ft.TextField(
            label="Дата рождения (ДДММГГГГ)",
            hint_text="Например: 15052021",
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        room_dropdown = ft.Dropdown(
            label="Палата / Локация",
            options=[ft.dropdown.Option(k, v) for k, v in rooms.items()],
            value="room_1",
        )

        diag_items = db.get_dictionary_items("diagnosis")
        op_items = db.get_dictionary_items("operation")

        diag_autocomplete = ft.AutoComplete(
            suggestions=[
                ft.AutoCompleteSuggestion(key=item, value=item)
                for item in diag_items
            ],
        )
        diag_container = ft.Column(
            [
                ft.Text("Планируемый диагноз:", weight=ft.FontWeight.BOLD, size=13),
                diag_autocomplete,
            ],
            spacing=2,
        )

        op_autocomplete = ft.AutoComplete(
            suggestions=[
                ft.AutoCompleteSuggestion(key=item, value=item)
                for item in op_items
            ],
        )
        op_container = ft.Column(
            [
                ft.Text("Планируемая операция:", weight=ft.FontWeight.BOLD, size=13),
                op_autocomplete,
            ],
            spacing=2,
        )

        tasks_field = ft.TextField(
            label="Задачи / Напоминалка",
            multiline=True,
            min_lines=2,
            hint_text="Взять согласие, анализы...",
        )

        def close_dlg(e=None):
            add_dialog.open = False
            page.update()

        def save_patient(e):
            if not fio_field.value or not fio_field.value.strip():
                fio_field.error_text = "Введите ФИО"
                page.update()
                return

            parsed_date = db.parse_ddmmyyyy(dob_field.value or "")
            b_date_iso = parsed_date.isoformat() if parsed_date else ""

            diag_val = getattr(diag_autocomplete, 'value', '') or ''
            op_val = getattr(op_autocomplete, 'value', '') or ''

            db.add_hospital_patient(
                fio=fio_field.value.strip(),
                birth_date_iso=b_date_iso,
                room_key=room_dropdown.value,
                diagnosis=diag_val,
                operation=op_val,
                tasks=tasks_field.value or "",
            )

            add_dialog.open = False
            refresh_hospital_view()

            snack = ft.SnackBar(ft.Text("Пациент успешно добавлен!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        add_dialog = ft.AlertDialog(
            title=ft.Text("Добавить пациента"),
            content=ft.Column(
                [
                    fio_field,
                    dob_field,
                    room_dropdown,
                    diag_container,
                    op_container,
                    tasks_field,
                ],
                tight=True,
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dlg),
                ft.Button("Сохранить", on_click=save_patient),
            ],
        )

        page.overlay.append(add_dialog)
        add_dialog.open = True
        page.update()

    # --- Настройки палат ---
    def open_settings(e):
        current_rooms = db.get_room_names()

        r1_input = ft.TextField(label="Палата 1", value=current_rooms.get("room_1", ""))
        r2_input = ft.TextField(label="Палата 2", value=current_rooms.get("room_2", ""))
        r3_input = ft.TextField(label="Палата 3", value=current_rooms.get("room_3", ""))
        r_other_input = ft.TextField(
            label="Другие", value=current_rooms.get("room_other", "")
        )

        def close_dialog(e=None):
            dialog.open = False
            page.update()

        def save_room_settings(e):
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE settings SET value = ? WHERE key = 'room_1'",
                    (r1_input.value,),
                )
                cursor.execute(
                    "UPDATE settings SET value = ? WHERE key = 'room_2'",
                    (r2_input.value,),
                )
                cursor.execute(
                    "UPDATE settings SET value = ? WHERE key = 'room_3'",
                    (r3_input.value,),
                )
                cursor.execute(
                    "UPDATE settings SET value = ? WHERE key = 'room_other'",
                    (r_other_input.value,),
                )
                conn.commit()

            nonlocal room_names
            room_names = db.get_room_names()
            dialog.open = False
            refresh_hospital_view()

            snack = ft.SnackBar(ft.Text("Названия палат обновлены!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Редактировать названия палат"),
            content=ft.Column(
                [r1_input, r2_input, r3_input, r_other_input], tight=True
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dialog),
                ft.Button("Сохранить", on_click=save_room_settings),
            ],
        )

        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    # --- Отрисовка списка палат и пациентов ---
    hospital_content = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    def refresh_hospital_view():
        rooms = db.get_room_names()
        patients = db.get_hospital_patients()

        hospital_content.controls.clear()

        hospital_content.controls.append(
            ft.Button(
                "Добавить пациента в отделение",
                icon=ft.Icons.ADD,
                on_click=open_add_patient_dialog,
            )
        )
        hospital_content.controls.append(ft.Divider())

        for r_key, r_name in rooms.items():
            room_patients = [p for p in patients if p["room_key"] == r_key]

            patient_cards = []
            for p in room_patients:
                age_str = db.format_age(p["birth_date"])
                age_display = f" ({age_str})" if age_str else ""

                # Функция-замыкание для обработки клика по конкретному пациенту
                def make_click_handler(pat):
                    return lambda e: open_patient_details_dialog(pat)

                if p["discharge_stage"] == 1:
                    card_content = ft.ListTile(
                        title=ft.Text(
                            f"{p['fio']}{age_display} — ВЫПИСАН",
                            style=ft.TextStyle(
                                decoration=ft.TextDecoration.LINE_THROUGH,
                                color=ft.Colors.GREY_600,
                            ),
                        ),
                        subtitle=ft.Text("Ожидает архивации (нажмите для 2-го шага)"),
                        on_click=make_click_handler(p),
                    )
                else:
                    status_badge = (
                        " [Прооперирован]" if p["is_operated"] else ""
                    )
                    diag_info = f"Диагноз: {p['diagnosis_planned'] or 'Не указан'}"
                    op_info = (
                        f"Операция: {p['operation_done'] or p['operation_planned'] or 'Не запланирована'}"
                    )
                    tasks_info = f"Задачи: {p['tasks']}" if p["tasks"] else ""

                    details = [
                        ft.Text(diag_info),
                        ft.Text(op_info),
                    ]
                    if tasks_info:
                        details.append(
                            ft.Text(tasks_info, color=ft.Colors.BLUE_700)
                        )

                    card_content = ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"{p['fio']}{age_display}{status_badge}",
                                    weight=ft.FontWeight.BOLD,
                                    size=16,
                                    color=ft.Colors.GREEN_800 if p["is_operated"] else ft.Colors.BLACK,
                                ),
                                *details,
                            ]
                        ),
                        padding=10,
                        on_click=make_click_handler(p),
                    )

                patient_cards.append(
                    ft.Card(
                        content=card_content,
                        margin=ft.Margin(bottom=8, left=0, top=0, right=0),
                    )
                )

            if not patient_cards:
                patient_cards.append(
                    ft.Text(
                        "Нет пациентов",
                        italic=True,
                        color=ft.Colors.GREY_500,
                    )
                )

            room_box = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            r_name,
                            weight=ft.FontWeight.BOLD,
                            size=17,
                            color=ft.Colors.BLUE_900,
                        ),
                        *patient_cards,
                    ]
                ),
                padding=12,
                border_radius=8,
                bgcolor=ft.Colors.BLUE_50,
                margin=ft.Margin(bottom=12, left=0, top=0, right=0),
            )

            hospital_content.controls.append(room_box)

        page.update()

    # --- Панели и Навигация ---
    page.appbar = ft.AppBar(
        leading=ft.Container(
            content=ft.Image(
                src="logo.png",  # Имя файла из папки assets
                fit="contain",
            ),
            padding=5,  # Небольшой отступ, чтобы иконка не прилипала к краям
        ),
        leading_width=40,  # Ширина зоны под логотип
        title=ft.Text("ЛОР Врач"),
        actions=[
            ft.IconButton(
                icon=ft.Icons.SETTINGS,
                tooltip="Настройки палат",
                on_click=open_settings,
            )
        ],
    )

# --- БЛОК 2: ЧАСТНЫЙ ЦЕНТР ---

    # Подробный диалог для частного центра (без выбора палаты, с возможностью добавить дату операции позже)
    def open_private_details_dialog(patient: dict):
        diag_planned_in = ft.TextField(
            label="Диагноз", value=patient["diagnosis_planned"] or ""
        )
        op_planned_in = ft.TextField(
            label="Планируемая операция", value=patient["operation_planned"] or ""
        )
        
        # Извлекаем дату операции, если она была сохранена в поле discharge_at или в описании
        op_date_in = ft.TextField(
            label="Дата операции (ДДММГГГГ)",
            value=patient["discharge_at"] or "",
            hint_text="Например: 25102026",
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        is_op_check = ft.Checkbox(
            label="Операция выполнена", value=bool(patient["is_operated"])
        )

        op_done_in = ft.TextField(
            label="Выполненная операция",
            value=patient["operation_done"] or patient["operation_planned"] or "",
            visible=bool(patient["is_operated"]),
        )
        intraop_in = ft.TextField(
            label="Осложнения",
            value=patient["intraop_complications"] or "",
            visible=bool(patient["is_operated"]),
        )

        def toggle_operated_fields(e):
            is_visible = is_op_check.value
            op_done_in.visible = is_visible
            intraop_in.visible = is_visible
            page.update()

        is_op_check.on_change = toggle_operated_fields

        def close_dlg(e=None):
            details_dialog.open = False
            page.update()

        def save_changes(e):
            parsed_op_date = db.parse_ddmmyyyy(op_date_in.value or "")
            op_date_str = parsed_op_date.strftime("%d.%m.%Y") if parsed_op_date else (op_date_in.value or "")

            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE patients SET
                        diagnosis_planned = ?,
                        operation_planned = ?,
                        is_operated = ?,
                        operation_done = ?,
                        intraop_complications = ?,
                        discharge_at = ?
                    WHERE id = ?
                """,
                    (
                        diag_planned_in.value or "",
                        op_planned_in.value or "",
                        1 if is_op_check.value else 0,
                        op_done_in.value or "",
                        intraop_in.value or "",
                        op_date_str,
                        patient["id"],
                    ),
                )
                conn.commit()

            details_dialog.open = False
            refresh_private_view()

        def process_archive(e):
            db.advance_discharge_stage(patient["id"], 1) # Сразу отправляем в архив
            details_dialog.open = False
            refresh_private_view()

            snack = ft.SnackBar(ft.Text("Запись отправлена в архив!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        details_dialog = ft.AlertDialog(
            title=ft.Text(f"Частный прием: {patient['fio']}"),
            content=ft.Column(
                [
                    diag_planned_in,
                    op_planned_in,
                    op_date_in,
                    is_op_check,
                    op_done_in,
                    intraop_in,
                    ft.Divider(),
                    ft.Button(
                        "Отправить в архив",
                        icon=ft.Icons.ARCHIVE,
                        icon_color=ft.Colors.RED_600,
                        on_click=process_archive,
                    ),
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dlg),
                ft.Button("Сохранить", on_click=save_changes),
            ],
        )

        page.overlay.append(details_dialog)
        details_dialog.open = True
        page.update()

    # Диалог добавления записи
    def open_add_private_dialog(e):
        fio_field = ft.TextField(label="ФИО пациента", autofocus=True)
        dob_field = ft.TextField(
            label="Дата рождения (ДДММГГГГ)",
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        diag_items = db.get_dictionary_items("diagnosis")
        op_items = db.get_dictionary_items("operation")

        diag_autocomplete = ft.AutoComplete(
            suggestions=[ft.AutoCompleteSuggestion(key=i, value=i) for i in diag_items]
        )
        op_autocomplete = ft.AutoComplete(
            suggestions=[ft.AutoCompleteSuggestion(key=i, value=i) for i in op_items]
        )

        op_date_field = ft.TextField(
            label="Дата операции (опционально)",
            hint_text="ДДММГГГГ (можно внести позже)",
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        def close_dlg(e=None):
            dlg.open = False
            page.update()

        def save_private(e):
            if not fio_field.value or not fio_field.value.strip():
                fio_field.error_text = "Введите ФИО"
                page.update()
                return

            parsed_dob = db.parse_ddmmyyyy(dob_field.value or "")
            dob_iso = parsed_dob.isoformat() if parsed_dob else ""

            parsed_op_date = db.parse_ddmmyyyy(op_date_field.value or "")
            op_date_display = parsed_op_date.strftime("%d.%m.%Y") if parsed_op_date else (op_date_field.value or "")

            diag_val = getattr(diag_autocomplete, "value", "") or ""
            op_val = getattr(op_autocomplete, "value", "") or ""

            db.add_private_patient(
                fio=fio_field.value.strip(),
                birth_date_iso=dob_iso,
                diagnosis=diag_val,
                operation=op_val,
                operation_date_iso=op_date_display,
            )

            dlg.open = False
            # Мгновенно обновляем интерфейс вкладки
            refresh_private_view()

            snack = ft.SnackBar(ft.Text("Запись добавлена!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Добавить запись (Частный центр)"),
            content=ft.Column(
                [
                    fio_field,
                    dob_field,
                    ft.Text("Диагноз:", weight=ft.FontWeight.BOLD, size=13),
                    diag_autocomplete,
                    ft.Text("Планируемая операция:", weight=ft.FontWeight.BOLD, size=13),
                    op_autocomplete,
                    op_date_field,
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dlg),
                ft.Button("Сохранить", on_click=save_private),
            ],
        )

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    private_content = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    def refresh_private_view():
        patients = db.get_private_patients()
        private_content.controls.clear()

        private_content.controls.append(
            ft.Button(
                "Добавить запись в частный центр",
                icon=ft.Icons.ADD,
                on_click=open_add_private_dialog,
            )
        )
        private_content.controls.append(ft.Divider())

        if not patients:
            private_content.controls.append(
                ft.Text("Нет активных записей", italic=True, color=ft.Colors.GREY_500)
            )

        for p in patients:
            age_str = db.format_age(p["birth_date"])
            age_display = f" ({age_str})" if age_str else ""

            def make_click_handler(pat):
                return lambda e: open_private_details_dialog(pat)

            status_badge = " [Выполнено]" if p["is_operated"] else ""
            diag_info = f"Диагноз: {p['diagnosis_planned'] or 'Не указан'}"
            
            op_date_text = f" (Дата: {p['discharge_at']})" if p['discharge_at'] else ""
            op_info = f"Операция: {p['operation_done'] or p['operation_planned'] or 'Не указана'}{op_date_text}"
            
            comp_info = f"Осложнения: {p['intraop_complications']}" if p["intraop_complications"] else ""

            details = [ft.Text(diag_info), ft.Text(op_info)]
            if comp_info:
                details.append(ft.Text(comp_info, color=ft.Colors.RED_700))

            card_content = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            f"{p['fio']}{age_display}{status_badge}",
                            weight=ft.FontWeight.BOLD,
                            size=16,
                            color=ft.Colors.GREEN_800 if p["is_operated"] else ft.Colors.BLACK,
                        ),
                        *details,
                    ]
                ),
                padding=10,
                on_click=make_click_handler(p),
            )

            private_content.controls.append(
                ft.Card(
                    content=card_content,
                    margin=ft.Margin(bottom=8, left=0, top=0, right=0),
                )
            )

        page.update()

# --- БЛОК 3: ВЫЕЗДЫ ---

    DISTRICT_LOCATIONS = [
        "МОКБ",
        "РНПЦ ДОГИ",
        "г. Жодино",
        "Березинский р-н",
        "Борисовский р-н",
        "Вилейский р-н",
        "Воложинский р-н",
        "Дзержинский р-н",
        "Клецкий р-н",
        "Копыльский р-н",
        "Крупский р-н",
        "Логойский р-н",
        "Любанский р-н",
        "Минский р-н",
        "Молодечненский р-н",
        "Мядельский р-н",
        "Несвижский р-н",
        "Пуховичский р-н",
        "Слуцкий р-н",
        "Смолевичский р-н",
        "Солигорский р-н",
        "Стародорожский р-н",
        "Столбцовский р-н",
        "Узденский р-н",
        "Червенский р-н",
        "Другое (вписать)",
    ]

    def open_district_details_dialog(patient: dict):
        purpose_in = ft.TextField(
            label="Цель выезда / Манипуляция", value=patient["operation_planned"] or ""
        )
        visit_date_in = ft.TextField(
            label="Дата выезда (ДДММГГГГ)",
            value=patient["discharge_at"] or "",
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        def close_dlg(e=None):
            details_dialog.open = False
            page.update()

        def save_changes(e):
            parsed_visit_date = db.parse_ddmmyyyy(visit_date_in.value or "")
            v_date_str = (
                parsed_visit_date.strftime("%d.%m.%Y")
                if parsed_visit_date
                else (visit_date_in.value or "")
            )

            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE patients SET
                        operation_planned = ?,
                        discharge_at = ?
                    WHERE id = ?
                """,
                    (
                        purpose_in.value or "",
                        v_date_str,
                        patient["id"],
                    ),
                )
                conn.commit()

            details_dialog.open = False
            refresh_district_view()

        def process_archive(e):
            db.advance_discharge_stage(patient["id"], 1)
            details_dialog.open = False
            refresh_district_view()

            snack = ft.SnackBar(ft.Text("Запись о выезде отправлена в архив!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        details_dialog = ft.AlertDialog(
            title=ft.Text(f"Выезд: {patient['fio']}"),
            content=ft.Column(
                [
                    ft.Text(f"Локация: {patient['room_key']}", weight=ft.FontWeight.BOLD),
                    visit_date_in,
                    purpose_in,
                    ft.Divider(),
                    ft.Button(
                        "Перенести в архив",
                        icon=ft.Icons.ARCHIVE,
                        icon_color=ft.Colors.RED_600,
                        on_click=process_archive,
                    ),
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dlg),
                ft.Button("Сохранить", on_click=save_changes),
            ],
        )

        page.overlay.append(details_dialog)
        details_dialog.open = True
        page.update()

    def open_add_district_dialog(e):
        fio_field = ft.TextField(label="ФИО пациента", autofocus=True)
        dob_field = ft.TextField(
            label="Дата рождения (ДДММГГГГ)",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        visit_date_field = ft.TextField(
            label="Дата выезда (ДДММГГГГ)",
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        location_dropdown = ft.Dropdown(
            label="Место выезда",
            options=[ft.dropdown.Option(loc) for loc in DISTRICT_LOCATIONS],
            value=DISTRICT_LOCATIONS[0],
        )
        custom_location_field = ft.TextField(
            label="Укажите место выезда",
            visible=False,
        )

        def on_location_change(e):
            custom_location_field.visible = location_dropdown.value == "Другое (вписать)"
            page.update()

        location_dropdown.on_change = on_location_change

        purpose_items = db.get_dictionary_items("operation")
        purpose_autocomplete = ft.AutoComplete(
            suggestions=[ft.AutoCompleteSuggestion(key=i, value=i) for i in purpose_items]
        )

        def close_dlg(e=None):
            dlg.open = False
            page.update()

        def save_district(e):
            if not fio_field.value or not fio_field.value.strip():
                fio_field.error_text = "Введите ФИО"
                page.update()
                return

            parsed_dob = db.parse_ddmmyyyy(dob_field.value or "")
            dob_iso = parsed_dob.isoformat() if parsed_dob else ""

            parsed_vdate = db.parse_ddmmyyyy(visit_date_field.value or "")
            vdate_display = (
                parsed_vdate.strftime("%d.%m.%Y")
                if parsed_vdate
                else (visit_date_field.value or "")
            )

            selected_loc = location_dropdown.value
            if selected_loc == "Другое (вписать)":
                selected_loc = custom_location_field.value or "Не указано"

            purpose_val = getattr(purpose_autocomplete, "value", "") or ""

            db.add_district_patient(
                fio=fio_field.value.strip(),
                birth_date_iso=dob_iso,
                visit_date_iso=vdate_display,
                location=selected_loc,
                purpose=purpose_val,
            )

            dlg.open = False
            refresh_district_view()

            snack = ft.SnackBar(ft.Text("Запись о выезде добавлена!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Добавить выезд"),
            content=ft.Column(
                [
                    fio_field,
                    dob_field,
                    visit_date_field,
                    location_dropdown,
                    custom_location_field,
                    ft.Text("Цель выезда / Манипуляция:", weight=ft.FontWeight.BOLD, size=13),
                    purpose_autocomplete,
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Отмена", on_click=close_dlg),
                ft.Button("Сохранить", on_click=save_district),
            ],
        )

        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    district_content = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    def refresh_district_view():
        patients = db.get_district_patients()
        district_content.controls.clear()

        district_content.controls.append(
            ft.Button(
                "Добавить выезд",
                icon=ft.Icons.ADD_LOCATION_ALT,
                on_click=open_add_district_dialog,
            )
        )
        district_content.controls.append(ft.Divider())

        if not patients:
            district_content.controls.append(
                ft.Text("Нет активных выездов", italic=True, color=ft.Colors.GREY_500)
            )

        for p in patients:
            age_str = db.format_age(p["birth_date"])
            age_display = f" ({age_str})" if age_str else ""

            def make_click_handler(pat):
                return lambda e: open_district_details_dialog(pat)

            loc_info = f"Локация: {p['room_key']}"
            date_info = f"Дата выезда: {p['discharge_at'] or 'Не указана'}"
            purpose_info = f"Цель/Манипуляция: {p['operation_planned'] or 'Не указана'}"

            card_content = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            f"{p['fio']}{age_display}",
                            weight=ft.FontWeight.BOLD,
                            size=16,
                        ),
                        ft.Text(loc_info, weight=ft.FontWeight.W_500),
                        ft.Text(date_info),
                        ft.Text(purpose_info),
                    ]
                ),
                padding=10,
                on_click=make_click_handler(p),
            )

            district_content.controls.append(
                ft.Card(
                    content=card_content,
                    margin=ft.Margin(bottom=8, left=0, top=0, right=0),
                )
            )

        page.update()

# --- БЛОК 4: ПОИСК И ЭКСПОРТ ---

    # Элементы поиска по ФИО
    fio_search_input = ft.TextField(
        label="ФИО пациента",
        hint_text="Введите фамилию...",
        expand=True,
    )
    fio_results_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    def search_by_fio(e):
        fio_results_column.controls.clear()
        query = fio_search_input.value.strip() if fio_search_input.value else ""
        
        if not query:
            snack = ft.SnackBar(ft.Text("Введите ФИО для поиска"))
            page.overlay.append(snack)
            snack.open = True
            page.update()
            return

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, context_type, fio, birth_date, diagnosis_planned, diagnosis_final, operation_planned, operation_done 
                FROM patients 
                WHERE fio LIKE ? 
                ORDER BY id DESC
                """,
                (f"%{query}%",),
            )
            results = [dict(row) for row in cursor.fetchall()]

        if not results:
            fio_results_column.controls.append(
                ft.Text("Пациенты не найдены", color=ft.Colors.GREY_500, italic=True)
            )
        else:
            context_labels = {
                "hospital": "Стационар",
                "private": "Частный центр",
                "district": "Выезд",
            }
            for item in results:
                ctx = context_labels.get(item["context_type"], item["context_type"])
                diag = item["diagnosis_final"] or item["diagnosis_planned"] or "Не указан"
                op = item["operation_done"] or item["operation_planned"] or "Не указана"
                age_str = db.format_age(item["birth_date"])
                age_disp = f" ({age_str})" if age_str else ""

                fio_results_column.controls.append(
                    ft.Card(
                        content=ft.ListTile(
                            leading=ft.Icon(ft.Icons.PERSON),
                            title=ft.Text(f"{item['fio']}{age_disp}"),
                            subtitle=ft.Text(f"Источник: {ctx}\nДиагноз: {diag}\nОперация: {op}"),
                        ),
                        margin=ft.Margin(bottom=6, left=0, top=0, right=0),
                    )
                )
        page.update()

    search_fio_btn = ft.Button("Найти", icon=ft.Icons.SEARCH, on_click=search_by_fio)

    # Элементы отчета Excel
    excel_query_input = ft.TextField(
        label="Диагноз или операция",
        hint_text="Например: Септопластика или Гайморит",
        expand=True,
    )
    
    excel_source_radio = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(value="hospital", label="Больница"),
            ft.Radio(value="private", label="Частный центр"),
        ]),
        value="hospital"
    )

    def generate_excel(e):
        q = excel_query_input.value.strip() if excel_query_input.value else ""
        if not q:
            snack = ft.SnackBar(ft.Text("Укажите диагноз или операцию для выгрузки"))
            page.overlay.append(snack)
            snack.open = True
            page.update()
            return

        source = excel_source_radio.value
        filename = f"Report_{source}_{q}.xlsx"
        
        success = db.export_to_excel(source, q, filename)
        
        if success:
            # Вызываем диалог отправки/сохранения
            export_and_share(filename)
        else:
            snack = ft.SnackBar(ft.Text("Записи по заданному критерию не найдены"))
            page.overlay.append(snack)
            snack.open = True
            page.update()

    excel_btn = ft.Button("Сформировать Excel", icon=ft.Icons.TABLE_CHART, on_click=generate_excel)

    # Карточка-напоминалка интерну
    # Диалог с предпросмотром картинки
    def generate_and_show_memo(e):
        filename = "intern_memo.png"
        success = db.generate_intern_memo_image(filename)
        
        if not success:
            snack = ft.SnackBar(ft.Text("Нет активных задач для формирования памятки!"))
            page.overlay.append(snack)
            snack.open = True
            page.update()
            return

        # Показываем предпросмотр и добавляем кнопку "Поделиться"
        memo_dialog = ft.AlertDialog(
            title=ft.Text("Памятка для интерна"),
            content=ft.Column([
                ft.Image(src=filename, width=400, fit="contain")
            ], tight=True, spacing=10),
            actions=[
                ft.TextButton("Отправить/Сохранить", on_click=lambda e: export_and_share(filename)),
                ft.TextButton("Закрыть", on_click=lambda e: setattr(memo_dialog, "open", False) or page.update())
            ]
        )
        page.overlay.append(memo_dialog)
        memo_dialog.open = True
        page.update()

    # Собираем вкладку
    tab_search = ft.Column(
        [
            # Секция 1: Поиск
            ft.Text("Поиск пациента по ФИО", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([fio_search_input, search_fio_btn]),
            ft.Container(content=fio_results_column, height=160),
            
            ft.Divider(),
            
            # Секция 2: Экспорт
            ft.Text("Формирование отчета в Excel", size=16, weight=ft.FontWeight.BOLD),
            excel_query_input,
            ft.Column(
                [
                    excel_source_radio,
                    excel_btn,
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.START,  # Заменено cross_axis_alignment на horizontal_alignment
            ),
            
            ft.Divider(),
            
            # Секция 3: Памятка интерну
            ft.Text("Памятка для интерна", size=16, weight=ft.FontWeight.BOLD),
            ft.Button(
                "Сформировать памятку (PNG)",
                icon=ft.Icons.PICTURE_IN_PICTURE,
                on_click=generate_and_show_memo,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    container = ft.Container(content=hospital_content, expand=True, padding=10)

    def nav_change(e):
        idx = e.control.selected_index
        tabs = [hospital_content, private_content, district_content, tab_search]
        container.content = tabs[idx]
        if idx == 1:
            refresh_private_view()
        elif idx == 2:
            refresh_district_view()
        page.update()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        on_change=nav_change,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.LOCAL_HOSPITAL, label="Отделение"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.BUSINESS, label="Частный центр"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.COMMUTE, label="Выезды"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.SEARCH, label="Поиск/Отчет"
            ),
        ],
    )

    page.add(
        ft.SafeArea(
            container,
            expand=True
        )
    )
    refresh_hospital_view()


ft.run(main, assets_dir="assets")
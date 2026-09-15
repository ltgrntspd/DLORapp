import datetime
import pandas as pd
import sqlite3
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import tempfile

DB_NAME = "hospital_app.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация таблиц базы данных."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """
        )

        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('room_1', 'Палата 1')"
        )
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('room_2', 'Палата 6')"
        )
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('room_3', 'Палата 8')"
        )
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('room_other', 'Другие отделения')"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_type TEXT NOT NULL,
                fio TEXT NOT NULL,
                birth_date TEXT,
                room_key TEXT,
                
                diagnosis_planned TEXT,
                diagnosis_final TEXT,
                operation_planned TEXT,
                operation_done TEXT,
                
                tasks TEXT,
                tasks_done INTEGER DEFAULT 0,
                
                is_operated INTEGER DEFAULT 0,
                intraop_complications TEXT,
                postop_features TEXT,
                
                discharge_stage INTEGER DEFAULT 0,
                
                district_name TEXT,
                action_type TEXT,
                
                created_at TEXT NOT NULL,
                discharge_at TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_dictionary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                value TEXT NOT NULL UNIQUE
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS districts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """
        )

        default_districts = [
            "Жодино", "Борисовский район", "Вилейский район", "Воложинский район",
            "Дзержинский район", "Клецкий район", "Копыльский район", "Крупский район",
            "Логойский район", "Любанский район", "Минский район", "Молодечненский район",
            "Мядельский район", "Несвижский район", "Пуховичский район", "Слуцкий район",
            "Смолевичский район", "Солигорский район", "Стародорожский район", "Столбцовский район",
            "Узденский район", "Червенский район", "МОКБ", "РНПЦ онкологии", "Прочее"
        ]

        for dist in default_districts:
            cursor.execute(
                "INSERT OR IGNORE INTO districts (name) VALUES (?)", (dist,)
            )

        conn.commit()


def parse_ddmmyyyy(date_str: str) -> Optional[datetime.date]:
    clean_str = "".join(filter(str.isdigit, date_str))
    if len(clean_str) != 8:
        return None
    try:
        day = int(clean_str[:2])
        month = int(clean_str[2:4])
        year = int(clean_str[4:8])
        return datetime.date(year, month, day)
    except ValueError:
        return None


def format_age(birth_date_str: str) -> str:
    if not birth_date_str:
        return ""
    try:
        b_date = datetime.date.fromisoformat(birth_date_str)
    except ValueError:
        return ""

    today = datetime.date.today()
    years = (
        today.year
        - b_date.year
        - ((today.month, today.day) < (b_date.month, b_date.day))
    )

    if years < 3:
        months = (today.year - b_date.year) * 12 + today.month - b_date.month
        if today.day < b_date.day:
            months -= 1

        y = months // 12
        m = months % 12

        if y == 0:
            return f"{m} мес."
        elif m == 0:
            return f"{y} г."
        else:
            return f"{y} г. {m} мес."
    else:
        return f"{years} л."


def add_to_dictionary(category: str, value: str):
    if not value or not value.strip():
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO auto_dictionary (category, value) VALUES (?, ?)",
            (category, value.strip()),
        )
        conn.commit()


def get_dictionary_items(category: str) -> List[str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM auto_dictionary WHERE category = ? ORDER BY value ASC",
            (category,),
        )
        return [row["value"] for row in cursor.fetchall()]


def add_hospital_patient(
    fio: str,
    birth_date_iso: str,
    room_key: str,
    diagnosis: str,
    operation: str,
    tasks: str,
):
    add_to_dictionary("diagnosis", diagnosis)
    add_to_dictionary("operation", operation)

    today_str = datetime.date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patients (
                context_type, fio, birth_date, room_key,
                diagnosis_planned, operation_planned, tasks, created_at
            ) VALUES ('hospital', ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fio,
                birth_date_iso,
                room_key,
                diagnosis,
                operation,
                tasks,
                today_str,
            ),
        )
        conn.commit()


def get_hospital_patients():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM patients 
            WHERE context_type = 'hospital' AND discharge_stage < 2
            ORDER BY id DESC
        """
        )
        return [dict(row) for row in cursor.fetchall()]


# --- Обновление и Выписка пациентов ---
def update_patient_details(
    p_id: int,
    room_key: str,
    diagnosis_planned: str,
    operation_planned: str,
    is_operated: int,
    operation_done: str,
    intraop_complications: str,
    postop_features: str,
    tasks: str,
):
    add_to_dictionary("diagnosis", diagnosis_planned)
    add_to_dictionary("operation", operation_planned)
    add_to_dictionary("operation", operation_done)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE patients SET
                room_key = ?,
                diagnosis_planned = ?,
                operation_planned = ?,
                is_operated = ?,
                operation_done = ?,
                intraop_complications = ?,
                postop_features = ?,
                tasks = ?
            WHERE id = ?
        """,
            (
                room_key,
                diagnosis_planned,
                operation_planned,
                is_operated,
                operation_done,
                intraop_complications,
                postop_features,
                tasks,
                p_id,
            ),
        )
        conn.commit()


def advance_discharge_stage(p_id: int, current_stage: int):
    new_stage = current_stage + 1
    today_str = datetime.date.today().isoformat() if new_stage >= 1 else None

    with get_connection() as conn:
        cursor = conn.cursor()
        if new_stage == 1:
            cursor.execute(
                "UPDATE patients SET discharge_stage = ?, discharge_at = ? WHERE id = ?",
                (new_stage, today_str, p_id),
            )
        else:
            cursor.execute(
                "UPDATE patients SET discharge_stage = ? WHERE id = ?",
                (new_stage, p_id),
            )
        conn.commit()

# --- ЧАСТНЫЙ ЦЕНТР ---

def add_private_patient(
    fio: str,
    birth_date_iso: str,
    diagnosis: str,
    operation: str,
    operation_date_iso: str,
):
    add_to_dictionary("diagnosis", diagnosis)
    add_to_dictionary("operation", operation)

    today_str = datetime.date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patients (
                context_type, fio, birth_date,
                diagnosis_planned, operation_planned, created_at
            ) VALUES ('private', ?, ?, ?, ?, ?)
        """,
            (
                fio,
                birth_date_iso,
                diagnosis,
                f"{operation} (Дата: {operation_date_iso})" if operation_date_iso else operation,
                today_str,
            ),
        )
        conn.commit()


def get_private_patients():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM patients 
            WHERE context_type = 'private' AND discharge_stage < 2
            ORDER BY id DESC
        """
        )
        return [dict(row) for row in cursor.fetchall()]

# --- ВЫЕЗДЫ ---

def add_district_patient(
    fio: str,
    birth_date_iso: str,
    visit_date_iso: str,
    location: str,
    purpose: str,
):
    add_to_dictionary("operation", purpose)

    today_str = datetime.date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patients (
                context_type, fio, birth_date, room_key,
                operation_planned, discharge_at, created_at
            ) VALUES ('district', ?, ?, ?, ?, ?, ?)
        """,
            (
                fio,
                birth_date_iso,
                location,
                purpose,
                visit_date_iso,
                today_str,
            ),
        )
        conn.commit()


def get_district_patients():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM patients 
            WHERE context_type = 'district' AND discharge_stage < 2
            ORDER BY id DESC
        """
        )
        return [dict(row) for row in cursor.fetchall()]


def get_app_shared_dir() -> str:
    """
    Возвращает общую директорию для файлов, доступную другим приложениям.
    ✅ ИСПРАВЛЕНО: Для кроссплатформенной работы
    """
    try:
        # Используем системную временную директорию как fallback
        return tempfile.gettempdir()
    except Exception:
        # Если не удалось получить — возвращаем текущую директорию
        return "."


def export_to_excel(source_type: str, query_text: str, output_filename: str = "report.xlsx") -> tuple:
    """
    Экспорт в Excel с проверкой зависимостей и доступным путём.
    Возвращает (успех: bool, filepath: str или error_message: str)
    """
    try:
        with db.get_connection() as conn:
            sql = """
                SELECT 
                    fio AS "ФИО",
                    birth_date AS "Дата рождения",
                    room_key AS "Палата/Локация",
                    diagnosis_planned AS "Диагноз планируемый",
                    diagnosis_final AS "Диагноз окончательный",
                    operation_planned AS "Операция планируемая",
                    operation_done AS "Операция выполненная",
                    intraop_complications AS "Осложнения",
                    postop_features AS "Особенности",
                    created_at AS "Дата создания",
                    discharge_at AS "Дата выписки/операции"
                FROM patients
                WHERE context_type = ? 
                  AND (diagnosis_planned LIKE ? OR diagnosis_final LIKE ? OR operation_planned LIKE ? OR operation_done LIKE ?)
            """
            param = f"%{query_text}%"
            df = pd.read_sql_query(sql, conn, params=(source_type, param, param, param, param))
            
            if df.empty:
                return (False, "Записи по заданному критерию не найдены")
            
            # ✅ ИСПРАВЛЕНО: Используем общую директорию
            shared_dir = get_app_shared_dir()
            full_path = os.path.join(shared_dir, output_filename)
            
            # Проверяем наличие необходимых библиотек
            try:
                df.to_excel(full_path, index=False)
                return (True, full_path)
            except ImportError as e:
                return (False, f"Недостаточно зависимостей для Excel: {e}. Установите openpyxl или xlsxwriter")
            
    except Exception as e:
        return (False, f"Ошибка экспорта: {str(e)}")


def generate_intern_memo_image(output_filename: str = "intern_memo.png") -> tuple:
    """
    ✅ ИСПРАВЛЕНО: Формирует PNG-картинку с задачами по палатам для интерна.
    Возвращает (успех: bool, filepath: str или error_message: str)
    """
    try:
        rooms = get_room_names()
        patients = get_hospital_patients()
        
        # Отбираем только пациентов с задачами
        targets = []
        for p in patients:
            tasks_text = (p.get("tasks") or "").strip()
            if tasks_text and p.get("discharge_stage", 0) == 0:
                targets.append(p)
                
        if not targets:
            return (False, "Нет пациентов с задачами")

        # Размеры и стили картинки
        width = 800
        padding = 30
        line_height = 28
        
        # Вычисляем высоту динамически в зависимости от количества строк
        total_lines = 3  # Заголовок и дата
        for p in targets:
            total_lines += 3  # Палата, ФИО/Возраст/Диагноз
            tasks_count = len([t for t in p["tasks"].split("\n") if t.strip()])
            total_lines += tasks_count + 1

        height = max(400, padding * 2 + total_lines * line_height)
        
        # Создаем холст (светло-голубой фон)
        image = Image.new("RGB", (width, height), color=(240, 244, 248))
        draw = ImageDraw.Draw(image)
        
        # ✅ ИСПРАВЛЕНО: Более надёжная загрузка шрифтов с fallback
        font_title = None
        font_body = None
        font_bold = None
        
        # Пытаемся загрузить системные шрифты для разных платформ
        font_paths = [
            "arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arial.ttf",
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_title = ImageFont.truetype(font_path, 22)
                    font_body = ImageFont.truetype(font_path, 16)
                    font_bold = ImageFont.truetype(font_path.replace(".ttf", "bd.ttf"), 17)
                    if not os.path.exists(font_bold.font_path):
                        font_bold = font_body  # fallback на обычный
                    break
                except:
                    continue
        
        if font_title is None:
            font_title = font_body = font_bold = ImageFont.load_default()

        y = padding
        
        # Шапка
        today_str = datetime.date.today().strftime("%d.%m.%Y")
        draw.text((padding, y), f"ПАМЯТКА ИНТЕРНУ — {today_str}", fill=(15, 23, 42), font=font_title)
        y += 40
        draw.line([(padding, y), (width - padding, y)], fill=(203, 213, 225), width=2)
        y += 20

        # Список пациентов
        for p in targets:
            r_name = rooms.get(p["room_key"], "Отделение")
            age_str = format_age(p["birth_date"])
            age_disp = f" ({age_str})" if age_str else ""
            diag = p["diagnosis_planned"] or "Диагноз не указан"

            # Заголовок пациента: Палата + ФИО
            draw.text((padding, y), f"• [{r_name}] {p['fio']}{age_disp}", fill=(30, 58, 138), font=font_bold)
            y += 24
            
            # Диагноз
            draw.text((padding + 15, y), f"Диагноз: {diag}", fill=(71, 85, 105), font=font_body)
            y += 24
            
            # Задачи
            tasks_list = [t.strip() for t in p["tasks"].split("\n") if t.strip()]
            for t in tasks_list:
                draw.text((padding + 25, y), f"[ ] {t}", fill=(15, 23, 42), font=font_body)
                y += 22
                
            y += 15  # Отступ между пациентами

        # ✅ ИСПРАВЛЕНО: Сохраняем в общую директорию
        shared_dir = get_app_shared_dir()
        full_path = os.path.join(shared_dir, output_filename)
        image.save(full_path)
        
        return (True, full_path)
        
    except Exception as e:
        return (False, f"Ошибка генерации изображения: {str(e)}")
    
def get_room_names() -> dict:
    """Возвращает словарь соответствия ключей палат и их названий из settings."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in cursor.fetchall()}
    

init_db()
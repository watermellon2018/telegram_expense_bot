"""
Утилиты для работы с проектами
"""

import os
import pandas as pd
import datetime
import shutil
import config

def get_projects_file_path(user_id):
    """
    Возвращает путь к файлу с проектами пользователя
    """
    from utils.excel import create_user_dir
    user_dir = create_user_dir(user_id)
    return os.path.join(user_dir, "projects.xlsx")

def create_projects_file(user_id):
    """
    Создает файл с проектами, если он не существует
    """
    projects_path = get_projects_file_path(user_id)
    
    if not os.path.exists(projects_path):
        # Создаем DataFrame для проектов
        projects_df = pd.DataFrame(columns=[
            'project_id', 'project_name', 'created_date', 'is_active'
        ])
        
        # Создаем DataFrame для активного проекта
        active_project_df = pd.DataFrame({
            'active_project_id': [None]
        })
        
        # Сохраняем в Excel
        with pd.ExcelWriter(projects_path, engine='openpyxl') as writer:
            projects_df.to_excel(writer, sheet_name='Projects', index=False)
            active_project_df.to_excel(writer, sheet_name='ActiveProject', index=False)
    
    return projects_path

def get_next_project_id(user_id):
    """
    Возвращает следующий доступный ID проекта
    """
    projects_path = create_projects_file(user_id)
    
    try:
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        
        if projects_df.empty:
            return 1
        
        return int(projects_df['project_id'].max()) + 1
    except Exception as e:
        print(f"Ошибка при получении следующего ID проекта: {e}")
        return 1

def create_project(user_id, project_name):
    """
    Создает новый проект
    """
    projects_path = create_projects_file(user_id)
    
    try:
        # Читаем текущие данные
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        active_project_df = pd.read_excel(projects_path, sheet_name='ActiveProject', engine='openpyxl')
        
        # Проверяем, существует ли проект с таким именем
        if not projects_df.empty and project_name.lower() in projects_df['project_name'].str.lower().values:
            return {
                'success': False,
                'message': f"Проект '{project_name}' уже существует"
            }
        
        # Получаем следующий ID
        project_id = get_next_project_id(user_id)
        
        # Создаем новую запись
        new_project = pd.DataFrame({
            'project_id': [project_id],
            'project_name': [project_name],
            'created_date': [datetime.datetime.now().strftime('%Y-%m-%d')],
            'is_active': [True]
        })
        
        projects_df = pd.concat([projects_df, new_project], ignore_index=True)
        
        # Создаем директорию для проекта
        from utils.excel import create_user_dir
        user_dir = create_user_dir(user_id)
        project_dir = os.path.join(user_dir, "projects", str(project_id))
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)
        
        # Сохраняем изменения
        with pd.ExcelWriter(projects_path, engine='openpyxl') as writer:
            projects_df.to_excel(writer, sheet_name='Projects', index=False)
            active_project_df.to_excel(writer, sheet_name='ActiveProject', index=False)
        
        return {
            'success': True,
            'project_id': project_id,
            'project_name': project_name,
            'message': f"Проект '{project_name}' создан"
        }
    except Exception as e:
        print(f"Ошибка при создании проекта: {e}")
        return {
            'success': False,
            'message': f"Ошибка при создании проекта: {e}"
        }

def get_all_projects(user_id):
    """
    Возвращает список всех проектов пользователя
    """
    projects_path = create_projects_file(user_id)
    
    try:
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        
        # Фильтруем только активные проекты
        active_projects = projects_df[projects_df['is_active'] == True]
        
        if active_projects.empty:
            return []
        
        return active_projects.to_dict('records')
    except Exception as e:
        print(f"Ошибка при получении списка проектов: {e}")
        return []

def get_project_by_id(user_id, project_id):
    """
    Возвращает проект по ID
    """
    projects_path = create_projects_file(user_id)
    
    try:
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        
        project = projects_df[
            (projects_df['project_id'] == project_id) & 
            (projects_df['is_active'] == True)
        ]
        
        if project.empty:
            return None
        
        return project.iloc[0].to_dict()
    except Exception as e:
        print(f"Ошибка при получении проекта по ID: {e}")
        return None

def get_project_by_name(user_id, project_name):
    """
    Возвращает проект по имени
    """
    projects_path = create_projects_file(user_id)
    
    try:
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        
        project = projects_df[
            (projects_df['project_name'].str.lower() == project_name.lower()) & 
            (projects_df['is_active'] == True)
        ]
        
        if project.empty:
            return None
        
        return project.iloc[0].to_dict()
    except Exception as e:
        print(f"Ошибка при получении проекта по имени: {e}")
        return None

def delete_project(user_id, project_id):
    """
    Удаляет проект (помечает как неактивный и удаляет файлы)
    """
    projects_path = create_projects_file(user_id)
    
    try:
        # Читаем текущие данные
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        active_project_df = pd.read_excel(projects_path, sheet_name='ActiveProject', engine='openpyxl')
        
        # Проверяем, существует ли проект
        project = projects_df[projects_df['project_id'] == project_id]
        
        if project.empty:
            return {
                'success': False,
                'message': "Проект не найден"
            }
        
        project_name = project.iloc[0]['project_name']
        
        # Помечаем проект как неактивный
        projects_df.loc[projects_df['project_id'] == project_id, 'is_active'] = False
        
        # Если удаляемый проект был активным, сбрасываем активный проект
        current_active = active_project_df.iloc[0]['active_project_id']
        if pd.notna(current_active) and int(current_active) == project_id:
            active_project_df.loc[0, 'active_project_id'] = None
        
        # Удаляем директорию проекта
        from utils.excel import create_user_dir
        user_dir = create_user_dir(user_id)
        project_dir = os.path.join(user_dir, "projects", str(project_id))
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
        
        # Сохраняем изменения
        with pd.ExcelWriter(projects_path, engine='openpyxl') as writer:
            projects_df.to_excel(writer, sheet_name='Projects', index=False)
            active_project_df.to_excel(writer, sheet_name='ActiveProject', index=False)
        
        return {
            'success': True,
            'message': f"Проект '{project_name}' удален"
        }
    except Exception as e:
        print(f"Ошибка при удалении проекта: {e}")
        return {
            'success': False,
            'message': f"Ошибка при удалении проекта: {e}"
        }

def set_active_project(user_id, project_id):
    """
    Устанавливает активный проект
    """
    projects_path = create_projects_file(user_id)
    
    try:
        # Читаем текущие данные
        projects_df = pd.read_excel(projects_path, sheet_name='Projects', engine='openpyxl')
        active_project_df = pd.read_excel(projects_path, sheet_name='ActiveProject', engine='openpyxl')
        
        # Если project_id is None, переключаемся на общие расходы
        if project_id is None:
            active_project_df.loc[0, 'active_project_id'] = None
            
            # Сохраняем изменения
            with pd.ExcelWriter(projects_path, engine='openpyxl') as writer:
                projects_df.to_excel(writer, sheet_name='Projects', index=False)
                active_project_df.to_excel(writer, sheet_name='ActiveProject', index=False)
            
            return {
                'success': True,
                'project_id': None,
                'project_name': None,
                'message': "Переключено на общие расходы"
            }
        
        # Проверяем, существует ли проект
        project = projects_df[
            (projects_df['project_id'] == project_id) & 
            (projects_df['is_active'] == True)
        ]
        
        if project.empty:
            return {
                'success': False,
                'message': "Проект не найден"
            }
        
        project_name = project.iloc[0]['project_name']
        
        # Устанавливаем активный проект
        active_project_df.loc[0, 'active_project_id'] = project_id
        
        # Сохраняем изменения
        with pd.ExcelWriter(projects_path, engine='openpyxl') as writer:
            projects_df.to_excel(writer, sheet_name='Projects', index=False)
            active_project_df.to_excel(writer, sheet_name='ActiveProject', index=False)
        
        return {
            'success': True,
            'project_id': project_id,
            'project_name': project_name,
            'message': f"Переключено на проект '{project_name}'"
        }
    except Exception as e:
        print(f"Ошибка при установке активного проекта: {e}")
        return {
            'success': False,
            'message': f"Ошибка при установке активного проекта: {e}"
        }

def get_active_project(user_id):
    """
    Возвращает информацию об активном проекте
    """
    projects_path = create_projects_file(user_id)
    
    try:
        active_project_df = pd.read_excel(projects_path, sheet_name='ActiveProject', engine='openpyxl')
        
        active_project_id = active_project_df.iloc[0]['active_project_id']
        
        # Если активный проект не установлен, возвращаем None
        if pd.isna(active_project_id):
            return None
        
        # Получаем информацию о проекте
        return get_project_by_id(user_id, int(active_project_id))
    except Exception as e:
        print(f"Ошибка при получении активного проекта: {e}")
        return None

def get_project_stats(user_id, project_id, year=None):
    """
    Возвращает статистику по проекту
    """
    from utils.excel import get_all_expenses
    
    if year is None:
        year = datetime.datetime.now().year
    
    try:
        expenses_df = get_all_expenses(user_id, year, project_id)
        
        if expenses_df is None or expenses_df.empty:
            return {
                'total': 0,
                'count': 0,
                'by_category': {}
            }
        
        total = expenses_df['amount'].sum()
        count = len(expenses_df)
        by_category = expenses_df.groupby('category')['amount'].sum().to_dict()
        
        return {
            'total': total,
            'count': count,
            'by_category': by_category
        }
    except Exception as e:
        print(f"Ошибка при получении статистики проекта: {e}")
        return {
            'total': 0,
            'count': 0,
            'by_category': {}
        }

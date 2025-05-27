"""
Модуль для тестирования функциональности Telegram-бота
"""

import os
import sys
import unittest
import datetime
import pandas as pd
from unittest.mock import MagicMock, patch

# Добавляем корневую директорию проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import excel, helpers, visualization
import config

class TestExcelFunctions(unittest.TestCase):
    """
    Тесты для функций работы с Excel
    """
    
    def setUp(self):
        """
        Подготовка к тестам
        """
        # Создаем временную директорию для тестов
        self.test_user_id = 123456789
        self.test_dir = os.path.join(config.DATA_DIR, str(self.test_user_id))
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
    
    def tearDown(self):
        """
        Очистка после тестов
        """
        # Удаляем тестовые файлы
        for file in os.listdir(self.test_dir):
            file_path = os.path.join(self.test_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
    
    def test_create_excel_file(self):
        """
        Тест создания Excel-файла
        """
        year = 2025
        excel_path = excel.create_excel_file(self.test_user_id, year)
        
        # Проверяем, что файл создан
        self.assertTrue(os.path.exists(excel_path))
        
        # Проверяем, что файл содержит нужные листы
        with pd.ExcelFile(excel_path) as xls:
            self.assertIn('Expenses', xls.sheet_names)
            self.assertIn('Categories', xls.sheet_names)
            self.assertIn('Budget', xls.sheet_names)
    
    def test_add_expense(self):
        """
        Тест добавления расхода
        """
        # Добавляем тестовый расход
        excel.add_expense(self.test_user_id, 100.0, "продукты", "тестовое описание")
        
        # Получаем путь к файлу
        year = datetime.datetime.now().year
        excel_path = excel.get_excel_path(self.test_user_id, year)
        
        # Проверяем, что файл создан
        self.assertTrue(os.path.exists(excel_path))
        
        # Проверяем, что расход добавлен
        expenses_df = pd.read_excel(excel_path, sheet_name='Expenses')
        self.assertEqual(len(expenses_df), 1)
        self.assertEqual(expenses_df.iloc[0]['amount'], 100.0)
        self.assertEqual(expenses_df.iloc[0]['category'], "продукты")
        self.assertEqual(expenses_df.iloc[0]['description'], "тестовое описание")
    
    def test_get_month_expenses(self):
        """
        Тест получения статистики расходов за месяц
        """
        # Добавляем тестовые расходы
        excel.add_expense(self.test_user_id, 100.0, "продукты", "тест 1")
        excel.add_expense(self.test_user_id, 200.0, "транспорт", "тест 2")
        excel.add_expense(self.test_user_id, 150.0, "продукты", "тест 3")
        
        # Получаем текущий месяц и год
        month = datetime.datetime.now().month
        year = datetime.datetime.now().year
        
        # Получаем статистику
        expenses = excel.get_month_expenses(self.test_user_id, month, year)
        
        # Проверяем результаты
        self.assertEqual(expenses['total'], 450.0)
        self.assertEqual(expenses['count'], 3)
        self.assertEqual(expenses['by_category']['продукты'], 250.0)
        self.assertEqual(expenses['by_category']['транспорт'], 200.0)
    
    def test_set_budget(self):
        """
        Тест установки бюджета
        """
        # Устанавливаем бюджет
        month = datetime.datetime.now().month
        year = datetime.datetime.now().year
        excel.set_budget(self.test_user_id, 1000.0, month, year)
        
        # Получаем путь к файлу
        excel_path = excel.get_excel_path(self.test_user_id, year)
        
        # Проверяем, что бюджет установлен
        budget_df = pd.read_excel(excel_path, sheet_name='Budget')
        month_budget = budget_df[budget_df['month'] == month]
        self.assertEqual(month_budget['budget'].values[0], 1000.0)

class TestHelperFunctions(unittest.TestCase):
    """
    Тесты для вспомогательных функций
    """
    
    def test_parse_add_command(self):
        """
        Тест парсинга команды добавления расхода
        """
        # Тест с командой /add
        result = helpers.parse_add_command("/add 100 продукты хлеб и молоко")
        self.assertEqual(result['amount'], 100.0)
        self.assertEqual(result['category'], "продукты")
        self.assertEqual(result['description'], "хлеб и молоко")
        
        # Тест без команды
        result = helpers.parse_add_command("200 транспорт такси")
        self.assertEqual(result['amount'], 200.0)
        self.assertEqual(result['category'], "транспорт")
        self.assertEqual(result['description'], "такси")
        
        # Тест без описания
        result = helpers.parse_add_command("300 развлечения")
        self.assertEqual(result['amount'], 300.0)
        self.assertEqual(result['category'], "развлечения")
        self.assertEqual(result['description'], "")
        
        # Тест с некорректным форматом
        result = helpers.parse_add_command("некорректный формат")
        self.assertIsNone(result)
    
    def test_format_month_expenses(self):
        """
        Тест форматирования статистики расходов за месяц
        """
        # Создаем тестовые данные
        expenses = {
            'total': 450.0,
            'count': 3,
            'by_category': {
                'продукты': 250.0,
                'транспорт': 200.0
            }
        }
        
        # Форматируем отчет
        month = 5  # Май
        year = 2025
        report = helpers.format_month_expenses(expenses, month, year)
        
        # Проверяем, что отчет содержит нужную информацию
        self.assertIn("Статистика расходов за May 2025", report)
        self.assertIn("Общая сумма: 450.00", report)
        self.assertIn("Количество транзакций: 3", report)
        self.assertIn("продукты: 250.00", report)
        self.assertIn("транспорт: 200.00", report)

def run_tests():
    """
    Запускает все тесты
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Добавляем тесты в набор
    suite.addTests(loader.loadTestsFromTestCase(TestExcelFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestHelperFunctions))
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_tests()
    print(f"Тесты {'успешно пройдены' if success else 'не пройдены'}")
    sys.exit(0 if success else 1)

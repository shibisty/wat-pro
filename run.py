"""
Запуск приложения: python run.py

Вся логика — в пакете qt_test_tool/, это просто удобная точка входа,
чтобы не набирать `python -m qt_test_tool.main`.
"""

from qt_test_tool.main import main

if __name__ == "__main__":
    main()

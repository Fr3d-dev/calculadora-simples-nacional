import openpyxl
from openpyxl.utils import get_column_letter

path = r"C:\Users\User\Documents\Guildahub plataforma\simples nacional\CALCULADORA SIMPLES.xlsx"
wb = openpyxl.load_workbook(path, data_only=False)

print("ABAS:", wb.sheetnames)
print("=" * 80)
for ws in wb.worksheets:
    print(f"\n### ABA: {ws.title}  (dims={ws.dimensions}, max_row={ws.max_row}, max_col={ws.max_column})")
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if v is not None and str(v).strip() != "":
                print(f"{cell.coordinate}: {repr(v)}")
    print("-" * 80)

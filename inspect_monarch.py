import inspect

from monarchmoney import MonarchMoney

print("Signatures:")
print(f"create_transaction: {inspect.signature(MonarchMoney.create_transaction)}")
print(f"update_transaction: {inspect.signature(MonarchMoney.update_transaction)}")

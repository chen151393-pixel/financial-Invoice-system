"""既有单位字典的只读映射；由管理员维护，不纳入新业务表迁移。"""

from sqlalchemy import column, table

unit_dictionary = table("unit_dictionary", column("unit_id"), column("unit_name"), column("enabled"))

from sqlalchemy import MetaData, Table, select, insert, update, delete, and_
from sqlalchemy.exc import NoSuchTableError

metadata = MetaData()

def get_table(db_engine, table_name: str) -> Table:
    metadata.clear()
    try:
        return Table(table_name, metadata, autoload_with=db_engine)
    except NoSuchTableError:
        raise

def primary_key_columns(t: Table):
    return [c for c in t.columns if c.primary_key]

def row_identity_filter(t: Table, pk_values: dict):
    pks = primary_key_columns(t)
    if not pks:
        raise ValueError("Tabelle hat keinen PRIMARY KEY; Edit/Delete ist unsicher. Bitte PK anlegen.")
    conds = []
    for c in pks:
        if c.name not in pk_values:
            raise ValueError(f"PK-Spalte fehlt: {c.name}")
        conds.append(c == pk_values[c.name])
    return and_(*conds)

def list_rows(db, t: Table, limit=200, offset=0):
    stmt = select(t).limit(limit).offset(offset)
    return db.execute(stmt).mappings().all()

def create_row(db, t: Table, data: dict):
    # Nur bekannte Spalten
    payload = {k: v for k, v in data.items() if k in t.c}
    stmt = insert(t).values(**payload)
    db.execute(stmt)
    db.commit()

def update_row(db, t: Table, pk_values: dict, data: dict):
    payload = {k: v for k, v in data.items() if k in t.c and k not in pk_values}
    stmt = update(t).where(row_identity_filter(t, pk_values)).values(**payload)
    db.execute(stmt)
    db.commit()

def delete_row(db, t: Table, pk_values: dict):
    stmt = delete(t).where(row_identity_filter(t, pk_values))
    db.execute(stmt)
    db.commit()

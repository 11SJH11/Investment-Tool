"""Preserve the existing Journal schema while admitting simulated forward results."""


def migrate(connection):
    sql = connection.execute("SELECT sql FROM sqlite_master WHERE name='journal_trades' AND type='table'").fetchone()[0]
    if "'forward_shadow'" in sql:
        return
    old = "'live_manual','paper_manual','replay','backtest'"
    if old not in sql:
        raise RuntimeError('Unrecognised Journal source constraint; migration stopped')
    # Do not risk cascading deletion in a database with custom incoming FKs.
    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        name = row[0].replace('"', '""')
        if any(fk[2] == 'journal_trades' for fk in connection.execute(f'PRAGMA foreign_key_list("{name}")')):
            raise RuntimeError('Custom Journal foreign key requires a preserving migration')
    objects = [r[0] for r in connection.execute("SELECT sql FROM sqlite_master WHERE tbl_name='journal_trades' AND type IN ('index','trigger') AND sql IS NOT NULL")]
    sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='journal_trades'").fetchone()
    ddl = sql.replace('journal_trades', 'journal_trades_forward', 1).replace(old, old+",'forward_shadow'", 1)
    connection.execute(ddl)
    columns = ','.join('"'+r[1].replace('"','""')+'"' for r in connection.execute('PRAGMA table_info(journal_trades)'))
    connection.execute(f'INSERT INTO journal_trades_forward({columns}) SELECT {columns} FROM journal_trades')
    if connection.execute(f'SELECT {columns} FROM journal_trades EXCEPT SELECT {columns} FROM journal_trades_forward').fetchone():
        raise RuntimeError('Journal migration preservation check failed')
    connection.execute('DROP TABLE journal_trades')
    connection.execute('ALTER TABLE journal_trades_forward RENAME TO journal_trades')
    for statement in objects:
        connection.execute(statement)
    if sequence:
        connection.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='journal_trades'", (sequence[0],))

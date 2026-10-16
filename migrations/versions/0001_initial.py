"""Initial RentFlow schema."""

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    for statement in SCHEMA:
        op.execute(statement)
    for table in ["documents", "evidence", "payments", "deposits", "audit", "assets"]:
        for action in ["UPDATE", "DELETE"]:
            op.execute(
                f"CREATE TRIGGER protect_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Archivierte Datensätze sind unveränderlich'); END"
            )


def downgrade():
    raise RuntimeError(
        "Destruktive Rückmigration gesperrt; geprüften Restore verwenden."
    )


SCHEMA = [
    '\nCREATE TABLE counters (\n\t"key" VARCHAR NOT NULL, \n\tvalue INTEGER NOT NULL, \n\tPRIMARY KEY ("key")\n)\n\n',
    "\nCREATE TABLE customers (\n\tid INTEGER NOT NULL, \n\tname VARCHAR NOT NULL, \n\temail VARCHAR NOT NULL, \n\tphone VARCHAR, \n\taddress TEXT, \n\tcontact VARCHAR, \n\tnotes TEXT, \n\tbusiness BOOLEAN, \n\trouting_id VARCHAR, \n\taddress_data JSON NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n",
    '\nCREATE TABLE login_attempts (\n\t"key" VARCHAR NOT NULL, \n\tcount INTEGER, \n\tsince VARCHAR NOT NULL, \n\tPRIMARY KEY ("key")\n)\n\n',
    '\nCREATE TABLE operations (\n\t"key" VARCHAR NOT NULL, \n\tfingerprint VARCHAR NOT NULL, \n\tresult JSON NOT NULL, \n\tPRIMARY KEY ("key")\n)\n\n',
    "\nCREATE TABLE packages (\n\tid INTEGER NOT NULL, \n\tname VARCHAR NOT NULL, \n\tdescription TEXT, \n\tcents INTEGER NOT NULL, \n\ttax VARCHAR, \n\tcomponents JSON NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n",
    '\nCREATE TABLE settings (\n\t"key" VARCHAR NOT NULL, \n\tvalue JSON NOT NULL, \n\tPRIMARY KEY ("key")\n)\n\n',
    "\nCREATE TABLE users (\n\tid INTEGER NOT NULL, \n\tname VARCHAR NOT NULL, \n\temail VARCHAR NOT NULL, \n\tpassword VARCHAR NOT NULL, \n\trole VARCHAR NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tversion INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (role IN ('admin','employee')), \n\tUNIQUE (email)\n)\n\n",
    "\nCREATE TABLE orders (\n\tid INTEGER NOT NULL, \n\tnumber VARCHAR NOT NULL, \n\tcustomer_id INTEGER NOT NULL, \n\tevent JSON NOT NULL, \n\tlines JSON NOT NULL, \n\trevision INTEGER NOT NULL, \n\toffer_id VARCHAR, \n\tcontract_id VARCHAR, \n\tinvoice_id VARCHAR, \n\tpacking_id VARCHAR, \n\thandover_id VARCHAR, \n\treturn_id VARCHAR, \n\thandover JSON NOT NULL, \n\treturned JSON NOT NULL, \n\thanded_at VARCHAR, \n\treturned_at VARCHAR, \n\tclosed_at VARCHAR, \n\tdeposit_cents INTEGER NOT NULL, \n\tcreated_at VARCHAR NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (deposit_cents >= 0), \n\tUNIQUE (number), \n\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n\tFOREIGN KEY(offer_id) REFERENCES documents (id), \n\tFOREIGN KEY(contract_id) REFERENCES documents (id), \n\tFOREIGN KEY(invoice_id) REFERENCES documents (id), \n\tFOREIGN KEY(packing_id) REFERENCES documents (id), \n\tFOREIGN KEY(handover_id) REFERENCES documents (id), \n\tFOREIGN KEY(return_id) REFERENCES documents (id)\n)\n\n",
    "\nCREATE TABLE assets (\n\tid VARCHAR NOT NULL, \n\torder_id INTEGER, \n\tfilename VARCHAR NOT NULL, \n\toriginal_name VARCHAR NOT NULL, \n\tmime VARCHAR NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\tcreated_at VARCHAR NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(order_id) REFERENCES orders (id), \n\tUNIQUE (filename)\n)\n\n",
    "\nCREATE TABLE audit (\n\tid INTEGER NOT NULL, \n\tactor_id INTEGER, \n\torder_id INTEGER, \n\taction VARCHAR NOT NULL, \n\tdetail JSON NOT NULL, \n\tcreated_at VARCHAR, \n\tprevious VARCHAR NOT NULL, \n\tdigest VARCHAR NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(order_id) REFERENCES orders (id)\n)\n\n",
    "\nCREATE TABLE deposits (\n\tid VARCHAR NOT NULL, \n\torder_id INTEGER NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tcents INTEGER NOT NULL, \n\tdate VARCHAR NOT NULL, \n\treason TEXT, \n\tactor_id INTEGER NOT NULL, \n\tcreated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tCHECK (cents > 0), \n\tCHECK (kind IN ('received','refunded','retained')), \n\tFOREIGN KEY(order_id) REFERENCES orders (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n",
    "\nCREATE TABLE documents (\n\tid VARCHAR NOT NULL, \n\torder_id INTEGER NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tversion INTEGER NOT NULL, \n\tnumber VARCHAR, \n\tsnapshot JSON NOT NULL, \n\tsha256 VARCHAR NOT NULL, \n\tfilename VARCHAR NOT NULL, \n\tcreated_at VARCHAR NOT NULL, \n\tactor_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (order_id, kind, version), \n\tFOREIGN KEY(order_id) REFERENCES orders (id), \n\tUNIQUE (number), \n\tUNIQUE (filename), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n",
    "\nCREATE TABLE evidence (\n\tid VARCHAR NOT NULL, \n\tdocument_id VARCHAR NOT NULL, \n\tasset_id VARCHAR NOT NULL, \n\tsigned_document_id VARCHAR, \n\tsigner VARCHAR NOT NULL, \n\tmethod VARCHAR NOT NULL, \n\tcreated_at VARCHAR NOT NULL, \n\tactor_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (document_id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id), \n\tFOREIGN KEY(asset_id) REFERENCES assets (id), \n\tFOREIGN KEY(signed_document_id) REFERENCES documents (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n",
    "\nCREATE TABLE items (\n\tid INTEGER NOT NULL, \n\tsku VARCHAR NOT NULL, \n\tname VARCHAR NOT NULL, \n\tcategory VARCHAR, \n\tdescription TEXT, \n\tcents INTEGER NOT NULL, \n\ttax VARCHAR NOT NULL, \n\treplacement_cents INTEGER, \n\timage_id VARCHAR, \n\tactive BOOLEAN, \n\tPRIMARY KEY (id), \n\tCHECK (cents >= 0 AND replacement_cents >= 0), \n\tUNIQUE (sku), \n\tFOREIGN KEY(image_id) REFERENCES assets (id)\n)\n\n",
    "\nCREATE TABLE jobs (\n\tid VARCHAR NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tdocument_id VARCHAR, \n\tasset_id VARCHAR, \n\tpayload JSON NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tattempts INTEGER NOT NULL, \n\terror TEXT, \n\tnext_at VARCHAR NOT NULL, \n\tcreated_at VARCHAR, \n\tfinished_at VARCHAR, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id), \n\tFOREIGN KEY(asset_id) REFERENCES assets (id)\n)\n\n",
    "\nCREATE TABLE payments (\n\tid VARCHAR NOT NULL, \n\tinvoice_id VARCHAR NOT NULL, \n\tcents INTEGER NOT NULL, \n\tdate VARCHAR NOT NULL, \n\tmethod VARCHAR NOT NULL, \n\treference TEXT, \n\treversal_of VARCHAR, \n\tactor_id INTEGER NOT NULL, \n\tcreated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tCHECK (cents != 0), \n\tFOREIGN KEY(invoice_id) REFERENCES documents (id), \n\tUNIQUE (reversal_of), \n\tFOREIGN KEY(reversal_of) REFERENCES payments (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n",
]

-- ERP-like schema for a technical wholesaler (synthetic data only).
-- Drops and recreates everything; run only via `task data`.

DROP TABLE IF EXISTS purchase_order_lines, purchase_orders, order_lines, orders, stock,
    products, customers, suppliers, dataset_meta CASCADE;

-- Key facts about the generated dataset, e.g. the reference date ("today" for the data).
CREATE TABLE dataset_meta (
    key   text PRIMARY KEY,
    value text NOT NULL
);

CREATE TABLE suppliers (
    id              integer PRIMARY KEY,
    supplier_no     text    NOT NULL UNIQUE,
    name            text    NOT NULL,
    country         text    NOT NULL,
    lead_time_days  integer NOT NULL CHECK (lead_time_days > 0)
);

CREATE TABLE products (
    id              integer PRIMARY KEY,
    sku             text          NOT NULL UNIQUE,
    name            text          NOT NULL,
    category        text          NOT NULL,
    unit            text          NOT NULL,          -- sales unit, e.g. 'Stück', 'Beutel', 'Rolle'
    supplier_id     integer       NOT NULL REFERENCES suppliers (id),
    purchase_price  numeric(12,2) NOT NULL CHECK (purchase_price > 0),
    list_price      numeric(12,2) NOT NULL CHECK (list_price > 0),
    min_order_qty   integer       NOT NULL CHECK (min_order_qty > 0),
    active          boolean       NOT NULL DEFAULT true
);

CREATE TABLE customers (
    id           integer PRIMARY KEY,
    customer_no  text NOT NULL UNIQUE,
    name         text NOT NULL,
    segment      text NOT NULL,                      -- e.g. 'Elektroinstallation', 'Maschinenbau'
    city         text NOT NULL,
    created_on   date NOT NULL
);

CREATE TABLE orders (
    id             integer PRIMARY KEY,
    order_no       text    NOT NULL UNIQUE,
    customer_id    integer NOT NULL REFERENCES customers (id),
    order_date     date    NOT NULL,
    promised_date  date    NOT NULL,
    shipped_date   date,
    status         text    NOT NULL CHECK (status IN ('open', 'shipped', 'cancelled'))
);
CREATE INDEX orders_order_date_idx ON orders (order_date);
CREATE INDEX orders_customer_idx ON orders (customer_id);

CREATE TABLE order_lines (
    id          integer PRIMARY KEY,
    order_id    integer       NOT NULL REFERENCES orders (id),
    product_id  integer       NOT NULL REFERENCES products (id),
    quantity    integer       NOT NULL CHECK (quantity > 0),
    unit_price  numeric(12,2) NOT NULL,              -- net sales price per unit after discount
    unit_cost   numeric(12,2) NOT NULL               -- purchase price per unit at time of sale
);
CREATE INDEX order_lines_order_idx ON order_lines (order_id);
CREATE INDEX order_lines_product_idx ON order_lines (product_id);

CREATE TABLE stock (
    product_id  integer PRIMARY KEY REFERENCES products (id),
    on_hand     integer NOT NULL CHECK (on_hand >= 0),
    reserved    integer NOT NULL CHECK (reserved >= 0)
);

CREATE TABLE purchase_orders (
    id             integer PRIMARY KEY,
    po_no          text    NOT NULL UNIQUE,
    supplier_id    integer NOT NULL REFERENCES suppliers (id),
    order_date     date    NOT NULL,
    expected_date  date    NOT NULL,
    received_date  date,
    status         text    NOT NULL CHECK (status IN ('open', 'received'))
);
CREATE INDEX purchase_orders_supplier_idx ON purchase_orders (supplier_id);

CREATE TABLE purchase_order_lines (
    id          integer PRIMARY KEY,
    po_id       integer       NOT NULL REFERENCES purchase_orders (id),
    product_id  integer       NOT NULL REFERENCES products (id),
    quantity    integer       NOT NULL CHECK (quantity > 0),
    unit_cost   numeric(12,2) NOT NULL
);
CREATE INDEX purchase_order_lines_po_idx ON purchase_order_lines (po_id);

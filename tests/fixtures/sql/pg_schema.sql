-- Schema for metadata-resolver live tests (PostgreSQL).
CREATE TABLE employees (
    emp_id      INTEGER PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    salary      NUMERIC(8, 2),
    hired_on    DATE,
    is_active   BOOLEAN DEFAULT TRUE
);

CREATE TABLE orders (
    order_id    BIGINT PRIMARY KEY,
    cust_id     INTEGER,
    amount      NUMERIC(12, 2),
    notes       TEXT
);

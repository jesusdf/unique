-- Schema for metadata-resolver live tests (MySQL).
CREATE TABLE employees (
    emp_id      INT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    salary      DECIMAL(8, 2),
    hired_on    DATE,
    is_active   TINYINT(1) DEFAULT 1
);

CREATE TABLE orders (
    order_id    BIGINT PRIMARY KEY,
    cust_id     INT,
    amount      DECIMAL(12, 2),
    notes       TEXT
);

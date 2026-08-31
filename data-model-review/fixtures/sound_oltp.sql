-- ---------------------------------------------------------------------------------
-- Fixture: a SOUND OLTP schema. The calibration control.
--
-- This one exists to catch over-firing. A rubric that produces 40 findings on a
-- competently built schema is useless in a different way from one that produces none
-- on a bad schema — it trains the reader to skim. selftest.py asserts zero BLOCKERs
-- and at most a handful of MAJORs here.
--
-- Conventions applied, and the source each comes from:
--   singular snake_case tables, {table}_id primary keys        SRC-PAGILA, SRC-SQLSG
--   business key unique alongside every surrogate              SRC-KAR-SAP1 (ID Required)
--   every FK declared, with an explicit ON DELETE              SRC-KAR-SAP1, SRC-SQLSG
--   every FK indexed                                           SRC-MSFT-WWI
--   COMMENT on every table and every non-obvious column        SRC-MSFT-WWI
--   audit columns on every table, actor as an FK               SRC-PAGILA, SRC-DAMA
--   money as NUMERIC with scale, plus a currency column        SRC-KAR-SAP1, SRC-KIM-DMT
--   timestamptz for instants, _at vs _date naming              SRC-DBT-STG, SRC-FOW-TIME
--   CHECK constraints on flags and small closed domains        SRC-SQLSG
--   partial unique index so soft delete does not block reuse   SRC-SOFTDEL
--   WITHOUT OVERLAPS equivalent via an exclusion constraint    SRC-SQL2011
--
-- @expect: NONE
-- ---------------------------------------------------------------------------------

-- Required by the EXCLUDE USING gist constraints below: btree_gist supplies the gist
-- operator classes for the scalar `=` comparisons. Without it this script does not run
-- on a clean database at all — also caught by a reviewer, and a reminder that "is the
-- DDL valid" is a question this skill's static rules do not ask.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE app_user (
    app_user_id     bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_login      varchar(64)     NOT NULL,
    display_name    varchar(200)    NOT NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_app_user_login UNIQUE (user_login)
);
COMMENT ON TABLE app_user IS 'A person or service account able to sign in. One row per account, not per person: a person who leaves and returns gets a second row.';
COMMENT ON COLUMN app_user.user_login IS 'Immutable sign-in identifier issued at account creation. Never reused after an account is closed.';

CREATE TABLE currency (
    currency_id     smallint        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code   char(3)         NOT NULL,
    currency_label  varchar(80)     NOT NULL,
    is_active       boolean         NOT NULL DEFAULT true,
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_currency_code UNIQUE (currency_code),
    CONSTRAINT ck_currency_code_iso CHECK (currency_code ~ '^[A-Z]{3}$')
);
COMMENT ON TABLE currency IS 'ISO 4217 currencies accepted by the system. Reference data, maintained by the finance team.';
COMMENT ON COLUMN currency.currency_code IS 'ISO 4217 alphabetic code. Stable; the label may be reworded without affecting stored references.';

CREATE TABLE payment_method (
    payment_method_id smallint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    method_code       varchar(20)   NOT NULL,
    method_label      varchar(80)   NOT NULL,
    is_active         boolean       NOT NULL DEFAULT true,
    last_update       timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT uq_payment_method_code UNIQUE (method_code)
);
COMMENT ON TABLE payment_method IS 'Ways a payment may be tendered. Reference data; codes are stable and referenced by external reconciliation files.';
COMMENT ON COLUMN payment_method.method_code IS 'Stable code shared with the bank reconciliation feed. Do not edit in place.';

CREATE TABLE customer (
    customer_id     bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_ref    varchar(20)     NOT NULL,
    legal_name      varchar(200)    NOT NULL,
    contact_email   varchar(320),
    credit_limit    numeric(18,2)   NOT NULL DEFAULT 0,
    currency_id     smallint        NOT NULL,
    onboarded_date  date            NOT NULL,
    deleted_at      timestamptz,
    created_by      bigint          NOT NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT fk_customer_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_customer_created_by FOREIGN KEY (created_by)
        REFERENCES app_user (app_user_id) ON DELETE RESTRICT ON UPDATE CASCADE
);
COMMENT ON TABLE customer IS 'An organisation the business sells to. One row per contracting entity, at the grain of a signed agreement.';
COMMENT ON COLUMN customer.customer_ref IS 'Externally issued account reference, printed on invoices. Unique among live customers; a soft-deleted value may be reissued.';
COMMENT ON COLUMN customer.credit_limit IS 'Maximum outstanding balance permitted, in the currency named by currency_id. Zero means no credit.';
COMMENT ON COLUMN customer.deleted_at IS 'Set when the customer is withdrawn. Soft delete is deliberate here because invoices must remain resolvable; the partial unique index below keeps customer_ref reusable.';
-- A genuinely PARTIAL unique index. The first draft of this fixture wrote
-- `(customer_ref, deleted_at)`, which is not the same thing and is not sound: NULLs
-- compare distinct in a unique index, so that form permits unlimited duplicate
-- customer_ref among live rows and constrains only the deleted ones. A reviewer working
-- without this skill caught it, and TEM-004 was extended to catch it too.
CREATE UNIQUE INDEX uq_customer_ref_live ON customer (customer_ref)
    WHERE deleted_at IS NULL;
CREATE INDEX ix_customer_currency ON customer (currency_id);
CREATE INDEX ix_customer_created_by ON customer (created_by);

CREATE TABLE product (
    product_id      bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code    varchar(30)     NOT NULL,
    product_label   varchar(200)    NOT NULL,
    unit_price      numeric(18,4)   NOT NULL,
    currency_id     smallint        NOT NULL,
    net_weight_kg   numeric(10,3),
    is_sellable     boolean         NOT NULL DEFAULT true,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_code UNIQUE (product_code),
    CONSTRAINT ck_product_price_nonneg CHECK (unit_price >= 0),
    CONSTRAINT fk_product_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT
);
COMMENT ON TABLE product IS 'A sellable item held in inventory. One row per catalogue entry; variants are separate rows.';
COMMENT ON COLUMN product.product_code IS 'Immutable catalogue code used by customers when ordering. Unique for all time, including withdrawn products.';
COMMENT ON COLUMN product.unit_price IS 'List price for one unit, in the currency named by currency_id, excluding tax.';
COMMENT ON COLUMN product.net_weight_kg IS 'Net weight of one unit in kilograms, as the column name states.';
CREATE INDEX ix_product_currency ON product (currency_id);

CREATE TABLE product_price_history (
    product_price_history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      bigint          NOT NULL,
    unit_price      numeric(18,4)   NOT NULL,
    currency_id     smallint        NOT NULL,
    valid_from      date            NOT NULL,
    valid_to        date,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT fk_pph_product FOREIGN KEY (product_id)
        REFERENCES product (product_id) ON DELETE CASCADE,
    CONSTRAINT fk_pph_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT,
    CONSTRAINT ck_pph_period CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT ex_pph_no_overlap EXCLUDE USING gist (
        product_id WITH =, daterange(valid_from, valid_to) WITH &&)
);
COMMENT ON TABLE product_price_history IS 'Effective-dated list price per product. One row per price period; valid_to NULL means still in force.';
COMMENT ON COLUMN product_price_history.valid_to IS 'Exclusive end of the period. NULL consistently represents an open period throughout this schema.';
CREATE INDEX ix_pph_product ON product_price_history (product_id, valid_from);
CREATE INDEX ix_pph_currency ON product_price_history (currency_id);

CREATE TABLE sales_order (
    sales_order_id  bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_ref       varchar(20)     NOT NULL,
    customer_id     bigint          NOT NULL,
    order_status    varchar(20)     NOT NULL,
    placed_at       timestamptz     NOT NULL,
    required_date   date,
    currency_id     smallint        NOT NULL,
    created_by      bigint          NOT NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_sales_order_ref UNIQUE (order_ref),
    CONSTRAINT ck_sales_order_status CHECK (
        order_status IN ('DRAFT', 'PLACED', 'CANCELLED', 'FULFILLED')),
    CONSTRAINT fk_sales_order_customer FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id) ON DELETE RESTRICT,
    CONSTRAINT fk_sales_order_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT,
    CONSTRAINT fk_sales_order_created_by FOREIGN KEY (created_by)
        REFERENCES app_user (app_user_id) ON DELETE RESTRICT
);
COMMENT ON TABLE sales_order IS 'A customer request to buy. One row per order header; lines live in sales_order_line.';
COMMENT ON COLUMN sales_order.order_ref IS 'Human-quoted order reference. Unique for all time so cancelled references are never reissued.';
COMMENT ON COLUMN sales_order.order_status IS 'Lifecycle state, constrained by ck_sales_order_status. The domain is closed and stable, so it is a CHECK rather than a reference table.';
COMMENT ON COLUMN sales_order.placed_at IS 'Instant the customer committed to the order, in UTC.';
COMMENT ON COLUMN sales_order.required_date IS 'Calendar date the customer needs delivery. A date, not an instant: no time component is meaningful.';
CREATE INDEX ix_sales_order_customer ON sales_order (customer_id, placed_at);
CREATE INDEX ix_sales_order_currency ON sales_order (currency_id);
CREATE INDEX ix_sales_order_created_by ON sales_order (created_by);

CREATE TABLE sales_order_line (
    sales_order_line_id bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sales_order_id  bigint          NOT NULL,
    line_seq        smallint        NOT NULL,
    product_id      bigint          NOT NULL,
    ordered_qty     numeric(12,3)   NOT NULL,
    unit_price      numeric(18,4)   NOT NULL,
    currency_id     smallint        NOT NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_sales_order_line_seq UNIQUE (sales_order_id, line_seq),
    CONSTRAINT ck_sales_order_line_qty CHECK (ordered_qty > 0),
    CONSTRAINT fk_sol_order FOREIGN KEY (sales_order_id)
        REFERENCES sales_order (sales_order_id) ON DELETE CASCADE,
    CONSTRAINT fk_sol_product FOREIGN KEY (product_id)
        REFERENCES product (product_id) ON DELETE RESTRICT,
    CONSTRAINT fk_sol_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT
);
COMMENT ON TABLE sales_order_line IS 'One product at one price on one order. Grain: order line. Quantity is in the product unit.';
COMMENT ON COLUMN sales_order_line.line_seq IS 'Position of the line within its order, unique per order. Not reused when a line is removed.';
COMMENT ON COLUMN sales_order_line.unit_price IS 'Price actually charged per unit, in the currency named by currency_id. Copied from product at order time so later list-price changes do not rewrite history.';
CREATE INDEX ix_sol_order ON sales_order_line (sales_order_id);
CREATE INDEX ix_sol_product ON sales_order_line (product_id);
CREATE INDEX ix_sol_currency ON sales_order_line (currency_id);

CREATE TABLE order_payment (
    order_payment_id bigint         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sales_order_id  bigint          NOT NULL,
    payment_method_id smallint      NOT NULL,
    paid_amount     numeric(18,2)   NOT NULL,
    currency_id     smallint        NOT NULL,
    settled_at      timestamptz     NOT NULL,
    bank_reference  varchar(64),
    created_by      bigint          NOT NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_order_payment_bank_ref UNIQUE (bank_reference),
    CONSTRAINT ck_order_payment_amount CHECK (paid_amount > 0),
    CONSTRAINT fk_op_order FOREIGN KEY (sales_order_id)
        REFERENCES sales_order (sales_order_id) ON DELETE RESTRICT,
    CONSTRAINT fk_op_method FOREIGN KEY (payment_method_id)
        REFERENCES payment_method (payment_method_id) ON DELETE RESTRICT,
    CONSTRAINT fk_op_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT,
    CONSTRAINT fk_op_created_by FOREIGN KEY (created_by)
        REFERENCES app_user (app_user_id) ON DELETE RESTRICT
);
COMMENT ON TABLE order_payment IS 'Money received against an order. One row per settled tender; partial payments are separate rows.';
COMMENT ON COLUMN order_payment.paid_amount IS 'Amount settled, in the currency named by currency_id. Always positive; refunds are modelled as a separate credit, not a negative payment.';
COMMENT ON COLUMN order_payment.bank_reference IS 'Reference from the bank feed. Unique where present, which is what makes reconciliation idempotent.';
CREATE INDEX ix_op_order ON order_payment (sales_order_id);
CREATE INDEX ix_op_method ON order_payment (payment_method_id);
CREATE INDEX ix_op_currency ON order_payment (currency_id);
CREATE INDEX ix_op_created_by ON order_payment (created_by);

CREATE TABLE customer_product_agreement (
    customer_id     bigint          NOT NULL,
    product_id      bigint          NOT NULL,
    agreed_price    numeric(18,4)   NOT NULL,
    currency_id     smallint        NOT NULL,
    valid_from      date            NOT NULL,
    valid_to        date,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT pk_cpa PRIMARY KEY (customer_id, product_id, valid_from),
    CONSTRAINT fk_cpa_customer FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id) ON DELETE CASCADE,
    CONSTRAINT fk_cpa_product FOREIGN KEY (product_id)
        REFERENCES product (product_id) ON DELETE CASCADE,
    CONSTRAINT fk_cpa_currency FOREIGN KEY (currency_id)
        REFERENCES currency (currency_id) ON DELETE RESTRICT,
    CONSTRAINT ex_cpa_no_overlap EXCLUDE USING gist (
        customer_id WITH =, product_id WITH =,
        daterange(valid_from, valid_to) WITH &&)
);
COMMENT ON TABLE customer_product_agreement IS 'Negotiated price for one product for one customer over one period. The association carries its own attributes, so it is an entity rather than a bare junction.';
COMMENT ON COLUMN customer_product_agreement.agreed_price IS 'Contracted unit price overriding product.unit_price for this customer during this period, in the currency named by currency_id.';
CREATE INDEX ix_cpa_product ON customer_product_agreement (product_id);
CREATE INDEX ix_cpa_currency ON customer_product_agreement (currency_id);

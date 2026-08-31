-- ---------------------------------------------------------------------------------
-- Fixture: a flawed dimensional (star) schema.
--
-- Exists to prove paradigm routing does something. Rules that are correct here are
-- wrong on an OLTP model and vice versa — a denormalised flattened dimension is a
-- Kimball recommendation and a 3NF violation, so a rubric that cannot tell the two
-- apart produces confident nonsense in one of them.
--
-- Note what must NOT fire here: PER-001 (unindexed FK) is excluded from the `dim`
-- paradigm, because a star schema's dimension keys are the join path by design and
-- indexing policy is a platform question, not a modelling defect.
--
-- Note also what correctly does NOT fire: NAM-010 stays quiet on fact_sales because
-- currency_key IS the currency dimension. That is the rule working, not a gap.
--
-- @expect: KEY-008 TEM-007 STR-006 REL-003 TYP-003 DOC-001 NUL-001
-- ---------------------------------------------------------------------------------

-- KEY-008: Type 2 dimension keyed on its natural key, so history cannot be stored.
-- TEM-007: effective dates with no current-row indicator.
CREATE TABLE dim_customer (
    customer_code   varchar(20)     NOT NULL PRIMARY KEY,
    customer_label  varchar(200)    NOT NULL,
    segment_label   varchar(60),
    country_label   varchar(60),
    valid_from      date            NOT NULL,
    valid_to        date
);

CREATE TABLE dim_date (
    date_key        integer         NOT NULL PRIMARY KEY,
    calendar_date   date            NOT NULL,
    fiscal_year     smallint        NOT NULL,
    fiscal_quarter  smallint        NOT NULL,
    month_label     varchar(20)     NOT NULL,
    CONSTRAINT uq_dim_date_calendar UNIQUE (calendar_date)
);
COMMENT ON TABLE dim_date IS 'Calendar date dimension. One row per day from 2015-01-01 to 2035-12-31.';

CREATE TABLE dim_product (
    product_sk      bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code    varchar(30)     NOT NULL,
    product_label   varchar(200)    NOT NULL,
    brand_label     varchar(80),
    category_label  varchar(80),
    subcategory_label varchar(80),
    CONSTRAINT uq_dim_product_code UNIQUE (product_code, valid_from)
);

-- STR-006: no grain statement. REL-003: centipede — hierarchy levels as dimensions.
-- TYP-003: money in double precision. NAM-010: no currency. NUL-001: -1 sentinel.
CREATE TABLE fact_sales (
    sales_sk            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key            integer     NOT NULL,
    customer_code       varchar(20) NOT NULL,
    product_sk          bigint      NOT NULL,
    brand_key           integer     NOT NULL,
    category_key        integer     NOT NULL,
    subcategory_key     integer     NOT NULL,
    country_key         integer     NOT NULL,
    region_key          integer     NOT NULL,
    city_key            integer     NOT NULL,
    channel_key         integer     NOT NULL,
    subchannel_key      integer     NOT NULL,
    salesperson_key     integer     NOT NULL,
    team_key            integer     NOT NULL,
    division_key        integer     NOT NULL,
    promotion_key       integer     NOT NULL,
    campaign_key        integer     NOT NULL,
    currency_key        integer     NOT NULL,
    payment_term_key    integer     NOT NULL,
    shipment_mode_key   integer     NOT NULL,
    warehouse_key       integer     NOT NULL,
    order_status_key    integer     NOT NULL,
    ordered_qty         numeric(12,3) NOT NULL,
    gross_amount        double precision NOT NULL,
    discount_amount     double precision NOT NULL,
    net_amount          double precision NOT NULL,
    legacy_order_key    integer     DEFAULT -1,
    CONSTRAINT fk_fs_date FOREIGN KEY (date_key)
        REFERENCES dim_date (date_key) ON DELETE RESTRICT,
    CONSTRAINT fk_fs_customer FOREIGN KEY (customer_code)
        REFERENCES dim_customer (customer_code) ON DELETE RESTRICT,
    CONSTRAINT fk_fs_product FOREIGN KEY (product_sk)
        REFERENCES dim_product (product_sk) ON DELETE RESTRICT
);

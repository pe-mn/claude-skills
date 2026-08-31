-- ---------------------------------------------------------------------------------
-- Fixture: flawed OLTP schema with PLANTED defects.
--
-- Each defect is annotated with the rule id it should trigger. selftest.py asserts
-- that every id listed here actually fires, which is what stops a check from rotting
-- into a no-op: a rule that silently stops detecting anything is worse than no rule,
-- because the clean report is read as good news.
--
-- @expect: STR-001 STR-003 STR-004 STR-005 KEY-001 KEY-002 KEY-003 KEY-005 KEY-007 INT-001
--      INT-002 INT-003 INT-004 INT-005 INT-006 TYP-001 TYP-002 TYP-004 TYP-005
--      TYP-008 TYP-009 NUL-001 NUL-002 NUL-003 REF-002 REF-003 REF-004 TEM-001 TEM-002
--      TEM-003 TEM-004 TEM-005 NAM-001 NAM-002 NAM-006 NAM-007 NAM-008 NAM-009 NAM-010
--      NAM-012 REL-001 PER-001 PER-003 GOV-001 GOV-002 DOC-001 DOC-002 DOC-003 EVO-001
--      LOC-001 LOC-002 LOC-003 LOC-004 CON-001 CON-002
-- ---------------------------------------------------------------------------------

-- Reference data: one generic lookup for everything -> REF-002, REF-003, REF-004
CREATE TABLE DOMAIN_DATA (
    DOMAIN_DATA_ID   NUMBER(10)      NOT NULL PRIMARY KEY,
    DOMAIN_TYPE_ID   NUMBER(10)      NOT NULL,
    DATA_VALUE       VARCHAR2(200),
    NAME_AR          VARCHAR2(200),
    NAME_EN          VARCHAR2(200),
    NAME_FR          VARCHAR2(200),          -- LOC-001: third language in parallel columns
    ACTIVE_FLAG      CHAR(1)         DEFAULT 'Y'   -- TYP-005: flag with no CHECK
);

-- KEY-002: no primary key at all. NUL-002: everything nullable.
CREATE TABLE AUDIT_TRAIL_STAGING (
    EVENT_TEXT       VARCHAR2(4000),
    EVENT_DATE       VARCHAR2(20),           -- TYP-001: date in a character type
    USER_NAME        VARCHAR2(100),
    ROW_COUNT_NUM    VARCHAR2(20)            -- TYP-002: quantity in a character type
);

-- The main entity. Several planted defects.
CREATE TABLE CUSTOMER (
    ID                  NUMBER(10)   NOT NULL PRIMARY KEY,   -- KEY-001, KEY-003
    CUST_NO             VARCHAR2(20),        -- NAM-008: synonym of CUSTOMER_NUMBER below
    CUSTOMER            VARCHAR2(200),       -- NAM-006: column named like its table
    NAME                VARCHAR2(200),       -- NAM-001: no object-class term. GOV-001
    NAME_AR             VARCHAR2(200),       -- LOC-002: AR present, EN absent here
    EMAIL               VARCHAR2(320),       -- GOV-001
    PASSWORD            VARCHAR2(100),       -- GOV-002: credential in plain text
    EMIRATES_ID         NUMBER(15),          -- TYP-008: formatted identifier as a number
    MOBILE              NUMBER(15),          -- TYP-008: phone as a number
    DATE_OF_BIRTH       DATE,                -- GOV-001
    BALANCE_AMOUNT      FLOAT,               -- TYP-003: money in FLOAT. NAM-010: no currency
    CREDIT_LIMIT        NUMBER,              -- TYP-004: no precision or scale
    STATUS              VARCHAR2(30),        -- NAM-001
    TAG_LIST            VARCHAR2(500),       -- REL-001: delimited list
    ADDRESS1            VARCHAR2(200),       -- STR-003: repeating group
    ADDRESS2            VARCHAR2(200),
    ADDRESS3            VARCHAR2(200),
    SPARE1              VARCHAR2(100),       -- EVO-001: placeholder columns
    SPARE2              VARCHAR2(100),
    UDF1                VARCHAR2(100),
    OWNER_TYPE          VARCHAR2(30),        -- INT-002: polymorphic pair with OWNER_ID
    OWNER_ID            NUMBER(10),
    REGION_ID           NUMBER(10),          -- INT-001: FK-shaped, no constraint
    IS_DELETED          CHAR(1)      DEFAULT 'N',   -- TEM-003/TEM-004
    CREATED_ON          TIMESTAMP,           -- TYP-009: no time zone
    CREATED_BY          VARCHAR2(100),       -- TEM-002: actor as free text
    UPDATED_DATE        TIMESTAMP,           -- CON-002/NAM-012: inconsistent + _DATE on a timestamp
    CONSTRAINT UQ_CUSTOMER_EMAIL UNIQUE (EMAIL)   -- TEM-004: ignores IS_DELETED
);

-- KEY-005: primary key on a mutable descriptive column.
CREATE TABLE REGION (
    REGION_NAME      VARCHAR2(100)   NOT NULL PRIMARY KEY,
    REGION_TYPE_ID   NUMBER(10),
    PARENT_REGION    VARCHAR2(100)
);

-- INT-006: referenced by CUSTOMER_ACCOUNT below but has no key.
CREATE TABLE ACCOUNT_TYPE_REF (
    ACCOUNT_TYPE_ID  NUMBER(10),
    DESCRIPTION      VARCHAR2(200)
);

CREATE TABLE CUSTOMER_ACCOUNT (
    CUSTOMER_ACCOUNT_ID NUMBER(10)  NOT NULL PRIMARY KEY,
    CUSTOMER_ID         NUMBER(10)  NOT NULL,
    ACCOUNT_TYPE_ID     NUMBER(10),
    CUSTOMER_NUMBER     VARCHAR2(20),        -- NAM-008 partner of CUST_NO
    OPENED_DATE         DATE,
    CLOSED_DATE         DATE,
    VALID_FROM          DATE,                -- TEM-005: no overlap constraint
    VALID_TO            DATE,
    CONSTRAINT FK_CA_CUST FOREIGN KEY (CUSTOMER_ID) REFERENCES CUSTOMER (ID),
    CONSTRAINT FK_CA_TYPE FOREIGN KEY (ACCOUNT_TYPE_ID)
        REFERENCES ACCOUNT_TYPE_REF (ACCOUNT_TYPE_ID)
);

-- STR-001: entity-attribute-value.
CREATE TABLE CUSTOMER_ATTRIBUTE (
    CUSTOMER_ATTRIBUTE_ID NUMBER(10) NOT NULL PRIMARY KEY,
    CUSTOMER_ID           NUMBER(10) NOT NULL,
    ATTRIBUTE_NAME        VARCHAR2(100),
    ATTRIBUTE_VALUE       VARCHAR2(4000),
    CONSTRAINT FK_CATTR_CUST FOREIGN KEY (CUSTOMER_ID) REFERENCES CUSTOMER (ID)
);

CREATE TABLE PRODUCT (
    PRODUCT_ID       NUMBER(10)      NOT NULL PRIMARY KEY,
    PRODUCT_CODE     VARCHAR2(30)    NOT NULL,
    PRODUCT_NAME     VARCHAR2(200),
    UNIT_PRICE       NUMBER(18,4),        -- NAM-010: no currency column on the table
    WEIGHT           NUMBER(10,3),        -- NAM-010: no unit column
    PRODUCT_TYPE     VARCHAR2(30)    DEFAULT 'UNKNOWN' NOT NULL,  -- NUL-003
    LEGACY_REF       NUMBER(10)      DEFAULT -1,                  -- NUL-001
    CONSTRAINT UQ_PRODUCT_CODE UNIQUE (PRODUCT_CODE)
);

-- KEY-007: associative table with no uniqueness on the pair.
CREATE TABLE CUSTOMER_PRODUCT (
    CUSTOMER_PRODUCT_ID NUMBER(10) NOT NULL PRIMARY KEY,
    CUSTOMER_ID         NUMBER(10) NOT NULL,
    PRODUCT_ID          NUMBER(10) NOT NULL,
    CONSTRAINT FK_CP_CUST FOREIGN KEY (CUSTOMER_ID) REFERENCES CUSTOMER (ID),
    CONSTRAINT FK_CP_PROD FOREIGN KEY (PRODUCT_ID) REFERENCES PRODUCT (PRODUCT_ID)
);


-- INT-004: self-referencing hierarchy with no cycle guard.
CREATE TABLE ORG_UNIT (
    ORG_UNIT_ID       NUMBER(10)     NOT NULL PRIMARY KEY,
    ORG_UNIT_NAME     VARCHAR2(200),
    PARENT_ORG_UNIT_ID NUMBER(10),
    CONSTRAINT FK_OU_PARENT FOREIGN KEY (PARENT_ORG_UNIT_ID)
        REFERENCES ORG_UNIT (ORG_UNIT_ID)
);

-- INT-005: the FK column type does not match the referenced key type. TEM-003: a
-- second soft-deleting table, so the inconsistency with the hard-deleting majority is
-- genuine rather than a single deliberate choice. CON-002: CREATE_DT is a third
-- spelling of the created-timestamp concept.
CREATE TABLE ORG_UNIT_CONTACT (
    ORG_UNIT_CONTACT_ID NUMBER(10)   NOT NULL PRIMARY KEY,
    ORG_UNIT_ID         VARCHAR2(20) NOT NULL,
    CONTACT_NAME        VARCHAR2(200),
    IS_DELETED          CHAR(1)      DEFAULT 'N',
    CREATE_DT           TIMESTAMP,
    CONSTRAINT FK_OUC_UNIT FOREIGN KEY (ORG_UNIT_ID)
        REFERENCES ORG_UNIT (ORG_UNIT_ID)
);

-- LOC-003: a Hijri date with no Gregorian column anywhere on the table to anchor it.
-- PER-003: the description asserts uniqueness that no constraint declares.
CREATE TABLE WAQF_DEED (
    WAQF_DEED_ID     NUMBER(10)      NOT NULL PRIMARY KEY,
    DEED_NUMBER      VARCHAR2(30),
    DEED_HIJRI_DATE  VARCHAR2(10),
    REGISTRAR_NAME   VARCHAR2(200)
);

-- CON-001: CUSTOMER_ID is NUMBER elsewhere, VARCHAR2 here.
-- NAM-009: same name, different type.
CREATE TABLE payment_txn (                  -- NAM-002: lowercase among UPPER tables
    payment_txn_id   NUMBER(10)     NOT NULL PRIMARY KEY,
    customer_id      VARCHAR2(20),
    "order"          VARCHAR2(30),          -- NAM-007: reserved word
    amount           FLOAT,                 -- TYP-003
    hijri_date       VARCHAR2(10),          -- LOC-003: Hijri with no Gregorian anchor
    gregorian_date   DATE,                  -- LOC-004 with hijri_date_2 below
    hijri_date_2     VARCHAR2(10),
    paid_date        TIMESTAMP              -- NAM-012
);

-- STR-004: table-per-period.
CREATE TABLE TXN_ARCHIVE_2023 (
    TXN_ARCHIVE_ID   NUMBER(10)     NOT NULL PRIMARY KEY,
    TXN_DATE         DATE,
    AMOUNT_VALUE     NUMBER(18,2)
);

CREATE TABLE TXN_ARCHIVE_2024 (
    TXN_ARCHIVE_ID   NUMBER(10)     NOT NULL PRIMARY KEY,
    TXN_DATE         DATE,
    AMOUNT_VALUE     NUMBER(18,2)
);

-- STR-005: very wide table (generated below to keep the fixture readable).
CREATE TABLE APPLICATION_FORM (
    APPLICATION_FORM_ID NUMBER(10) NOT NULL PRIMARY KEY,
    F001 VARCHAR2(200), F002 VARCHAR2(200), F003 VARCHAR2(200), F004 VARCHAR2(200),
    F005 VARCHAR2(200), F006 VARCHAR2(200), F007 VARCHAR2(200), F008 VARCHAR2(200),
    F009 VARCHAR2(200), F010 VARCHAR2(200), F011 VARCHAR2(200), F012 VARCHAR2(200),
    F013 VARCHAR2(200), F014 VARCHAR2(200), F015 VARCHAR2(200), F016 VARCHAR2(200),
    F017 VARCHAR2(200), F018 VARCHAR2(200), F019 VARCHAR2(200), F020 VARCHAR2(200),
    F021 VARCHAR2(200), F022 VARCHAR2(200), F023 VARCHAR2(200), F024 VARCHAR2(200),
    F025 VARCHAR2(200), F026 VARCHAR2(200), F027 VARCHAR2(200), F028 VARCHAR2(200),
    F029 VARCHAR2(200), F030 VARCHAR2(200), F031 VARCHAR2(200), F032 VARCHAR2(200),
    F033 VARCHAR2(200), F034 VARCHAR2(200), F035 VARCHAR2(200), F036 VARCHAR2(200),
    F037 VARCHAR2(200), F038 VARCHAR2(200), F039 VARCHAR2(200), F040 VARCHAR2(200),
    F041 VARCHAR2(200), F042 VARCHAR2(200), F043 VARCHAR2(200), F044 VARCHAR2(200),
    F045 VARCHAR2(200), F046 VARCHAR2(200), F047 VARCHAR2(200), F048 VARCHAR2(200),
    F049 VARCHAR2(200), F050 VARCHAR2(200), F051 VARCHAR2(200), F052 VARCHAR2(200),
    F053 VARCHAR2(200), F054 VARCHAR2(200), F055 VARCHAR2(200), F056 VARCHAR2(200),
    F057 VARCHAR2(200), F058 VARCHAR2(200), F059 VARCHAR2(200), F060 VARCHAR2(200),
    F061 VARCHAR2(200), F062 VARCHAR2(200), F063 VARCHAR2(200), F064 VARCHAR2(200)
);

-- Only one table is documented, so DOC-001 fires broadly and DOC-002 reports coverage.
COMMENT ON TABLE PRODUCT IS 'A sellable item held in inventory. One row per product, at catalogue grain.';
COMMENT ON COLUMN PRODUCT.PRODUCT_ID IS 'The product id';   -- DOC-003: restates the name
COMMENT ON COLUMN PRODUCT.PRODUCT_CODE IS 'Immutable external catalogue code. Unique across all products.';  -- correctly NOT a PER-003 finding: UQ_PRODUCT_CODE declares it
COMMENT ON COLUMN WAQF_DEED.DEED_NUMBER IS 'Registry deed number. Unique per registrar office.';  -- PER-003: asserted, never declared

-- INT-003: no ON DELETE declared on any of the FKs above.
-- PER-001: FK columns are unindexed; only these two indexes exist.
CREATE INDEX IX_CUSTOMER_STATUS ON CUSTOMER (STATUS);
CREATE INDEX IX_PRODUCT_NAME ON PRODUCT (PRODUCT_NAME);

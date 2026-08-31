-- ---------------------------------------------------------------------------------
-- Fixture: coverage for rules the three narrative fixtures do not exercise.
--
-- This one makes no attempt to look like a real schema. Its only job is to keep the
-- long tail of checks alive, because a check nobody exercises is a check that can rot
-- into a no-op and make a report cleaner without anyone noticing. Readability is not a
-- goal here; coverage is.
--
-- @expect: KEY-004 KEY-006 NAM-003 NAM-004 NAM-011 PER-002 REF-001 REF-005 TEM-006 TYP-006
--      TYP-007 INT-007 STR-002
-- ---------------------------------------------------------------------------------

-- STR-002 prescreen: an entity name that names no business concept. Tier B, so this
-- arrives as a candidate for adjudication rather than a scored finding.
CREATE TABLE generic (
    generic_id      bigint          NOT NULL PRIMARY KEY,
    entity_kind     varchar(30)     NOT NULL,
    payload_label   varchar(200),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_generic_kind_label UNIQUE (entity_kind, payload_label)
);
COMMENT ON TABLE generic IS 'Catch-all store used by three unrelated features. Grain: one row per whatever the feature needed.';
COMMENT ON COLUMN generic.entity_kind IS 'Which feature owns this row.';

-- KEY-004: five-column composite primary key, and not a junction table.
-- KEY-006: a key column in an approximate numeric type.
CREATE TABLE meter_reading (
    site_code       varchar(10)     NOT NULL,
    meter_code      varchar(10)     NOT NULL,
    register_code   varchar(10)     NOT NULL,
    read_date       date            NOT NULL,
    read_sequence   double precision NOT NULL,
    read_value      numeric(14,3)   NOT NULL,
    reading_note    varchar(200),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT pk_meter_reading PRIMARY KEY
        (site_code, meter_code, register_code, read_date, read_sequence)
);
COMMENT ON TABLE meter_reading IS 'One register reading taken at one meter on one date. Grain: reading.';
COMMENT ON COLUMN meter_reading.read_value IS 'Register value as displayed, in the register unit.';

-- NAM-004: tbl_ prefix. NAM-011: an identifier over 30 bytes.
-- TYP-006: an unbounded text column in a unique position.
CREATE TABLE tbl_document_revision_control_register (
    document_revision_control_register_id bigint NOT NULL PRIMARY KEY,
    document_body   text            NOT NULL,
    revision_label  varchar(40)     NOT NULL,
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_body UNIQUE (document_body)
);
COMMENT ON TABLE tbl_document_revision_control_register IS 'A stored revision of a document. Grain: one revision.';
COMMENT ON COLUMN tbl_document_revision_control_register.document_body IS 'Full text of the revision as submitted.';
COMMENT ON COLUMN tbl_document_revision_control_register.revision_label IS 'Label shown to users, e.g. Rev C.';

-- NAM-003: plural, among singular tables elsewhere in this fixture.
-- TYP-007: blanket maximum-width text columns.
CREATE TABLE submitted_forms (
    submitted_forms_id bigint       NOT NULL PRIMARY KEY,
    payload_one     varchar(4000),
    payload_two     varchar(4000),
    payload_three   varchar(4000),
    payload_four    varchar(4000),
    last_update     timestamptz     NOT NULL DEFAULT now()
);
COMMENT ON TABLE submitted_forms IS 'Raw submitted form payloads awaiting parsing. Grain: one submission.';
COMMENT ON COLUMN submitted_forms.payload_one IS 'First payload fragment as received from the portal.';

-- PER-002: several indexes leading with the same column, plus too many overall.
CREATE TABLE shipment (
    shipment_id     bigint          NOT NULL PRIMARY KEY,
    carrier_code    varchar(10)     NOT NULL,
    dispatched_date date            NOT NULL,
    arrived_date    date,
    weight_kg       numeric(10,3),
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_shipment_carrier_dispatch UNIQUE (carrier_code, dispatched_date, shipment_id)
);
COMMENT ON TABLE shipment IS 'A consignment moving from origin to destination. Grain: one shipment.';
COMMENT ON COLUMN shipment.weight_kg IS 'Gross weight in kilograms, as the column name states.';
CREATE INDEX ix_shipment_carrier_a ON shipment (carrier_code, dispatched_date);
CREATE INDEX ix_shipment_carrier_b ON shipment (carrier_code, arrived_date);
CREATE INDEX ix_shipment_carrier_c ON shipment (carrier_code);
CREATE INDEX ix_shipment_dispatched ON shipment (dispatched_date);
CREATE INDEX ix_shipment_arrived ON shipment (arrived_date);
CREATE INDEX ix_shipment_weight ON shipment (weight_kg);
CREATE INDEX ix_shipment_last_update ON shipment (last_update);
CREATE INDEX ix_shipment_id_carrier ON shipment (shipment_id, carrier_code);
CREATE INDEX ix_shipment_carrier_weight ON shipment (carrier_code, weight_kg);

-- REF-001: three different lookup shapes in one model.
CREATE TABLE lk_carrier (
    lk_carrier_id   smallint        NOT NULL PRIMARY KEY,
    code            varchar(10)     NOT NULL,
    label           varchar(80)     NOT NULL,
    is_active       boolean         NOT NULL DEFAULT true,
    CONSTRAINT uq_lk_carrier_code UNIQUE (code)
);
COMMENT ON TABLE lk_carrier IS 'Carriers available for dispatch. Reference data.';

CREATE TABLE lk_incoterm (
    lk_incoterm_id  smallint        NOT NULL PRIMARY KEY,
    code            varchar(10)     NOT NULL,
    description     varchar(200),
    CONSTRAINT uq_lk_incoterm_code UNIQUE (code)
);
COMMENT ON TABLE lk_incoterm IS 'Incoterms recognised on shipping documents. Reference data.';

CREATE TABLE lk_package_type (
    lk_package_type_id smallint     NOT NULL PRIMARY KEY,
    name            varchar(80)     NOT NULL
);
COMMENT ON TABLE lk_package_type IS 'Ways goods may be packaged. Reference data.';

-- REF-005: a long literal value list hard-coded in a CHECK constraint.
-- TEM-006: valid_to open-ended as NULL here and as a high sentinel in the next table.
CREATE TABLE tariff_band (
    tariff_band_id  bigint          NOT NULL PRIMARY KEY,
    band_code       varchar(20)     NOT NULL,
    band_category   varchar(20)     NOT NULL,
    valid_from      date            NOT NULL,
    valid_to        date,
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_tariff_band_code UNIQUE (band_code, valid_from),
    CONSTRAINT ck_tariff_band_category CHECK (band_category IN
        ('DOMESTIC', 'COMMERCIAL', 'INDUSTRIAL', 'AGRICULTURAL', 'GOVERNMENT',
         'CHARITABLE', 'DIPLOMATIC', 'TRANSIT'))
);
COMMENT ON TABLE tariff_band IS 'Effective-dated tariff band. Grain: one band per period.';
COMMENT ON COLUMN tariff_band.band_category IS 'Broad tariff class, constrained by ck_tariff_band_category.';

CREATE TABLE tariff_rate (
    tariff_rate_id  bigint          NOT NULL PRIMARY KEY,
    tariff_band_id  bigint          NOT NULL,
    rate_per_unit   numeric(12,6)   NOT NULL,
    currency_code   char(3)         NOT NULL,
    valid_from      date            NOT NULL,
    valid_to        date            NOT NULL DEFAULT '9999-12-31',
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_tariff_rate UNIQUE (tariff_band_id, valid_from),
    CONSTRAINT fk_tariff_rate_band FOREIGN KEY (tariff_band_id)
        REFERENCES tariff_band (tariff_band_id) ON DELETE CASCADE
);
COMMENT ON TABLE tariff_rate IS 'Effective-dated rate within a band. Grain: one rate per period.';
COMMENT ON COLUMN tariff_rate.rate_per_unit IS 'Charge per consumed unit, in the currency named by currency_code.';
CREATE INDEX ix_tariff_rate_band ON tariff_rate (tariff_band_id, valid_from);

-- INT-007: mutually mandatory foreign keys, so neither row can be inserted first.
CREATE TABLE contract_header (
    contract_header_id bigint       NOT NULL PRIMARY KEY,
    contract_ref    varchar(30)     NOT NULL,
    primary_schedule_id bigint      NOT NULL,
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_header_ref UNIQUE (contract_ref),
    CONSTRAINT fk_ch_schedule FOREIGN KEY (primary_schedule_id)
        REFERENCES contract_schedule (contract_schedule_id) ON DELETE RESTRICT
);
COMMENT ON TABLE contract_header IS 'A signed contract. Grain: one contract.';
COMMENT ON COLUMN contract_header.primary_schedule_id IS 'The schedule treated as authoritative for pricing.';
CREATE INDEX ix_ch_schedule ON contract_header (primary_schedule_id);

CREATE TABLE contract_schedule (
    contract_schedule_id bigint     NOT NULL PRIMARY KEY,
    contract_header_id bigint       NOT NULL,
    schedule_seq    smallint        NOT NULL,
    last_update     timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_schedule UNIQUE (contract_header_id, schedule_seq),
    CONSTRAINT fk_cs_header FOREIGN KEY (contract_header_id)
        REFERENCES contract_header (contract_header_id) ON DELETE CASCADE
);
COMMENT ON TABLE contract_schedule IS 'A priced schedule attached to a contract. Grain: one schedule.';
COMMENT ON COLUMN contract_schedule.schedule_seq IS 'Position of the schedule within its contract.';
CREATE INDEX ix_cs_header ON contract_schedule (contract_header_id);

-- Контракт публичного слоя глазами витрины (копия состава из T-60,
-- `showcase/layer.sql` в WOW_claude_datacollector).
--
-- Зачем копия. Сервис живёт в своём репозитории и в тестах не может дотянуться
-- до сборщика, а шов 3 требует засеянной базы витрины. Источник правды по
-- составу — спека (`docs/showcase-spec-live-site.md`, раздел «Публичный слой»),
-- и расходиться этот файл с ней не имеет права: разъехались — правится спека,
-- потом оба репозитория.
--
-- {schema} подставляется фикстурой.

CREATE SCHEMA "{schema}";

CREATE TABLE "{schema}".channel (
    id                   BIGINT PRIMARY KEY,
    platform             TEXT NOT NULL,
    username             TEXT NOT NULL,
    username_lower       TEXT NOT NULL,
    url                  TEXT,
    display_name         TEXT,
    description          TEXT,
    avatar_file          TEXT,
    blogger_id           BIGINT,
    blogger_has_siblings BOOLEAN NOT NULL DEFAULT FALSE,

    subscribers          BIGINT,
    views_avg            INTEGER,
    coverage_ratio       DOUBLE PRECISION,
    er_percent           DOUBLE PRECISION,

    posts_30d            INTEGER NOT NULL DEFAULT 0,
    ads_30d              INTEGER NOT NULL DEFAULT 0,
    ad_share_30d         DOUBLE PRECISION,

    views_organic        BIGINT,
    views_ad             BIGINT,
    views_drop           DOUBLE PRECISION,
    views_spread         DOUBLE PRECISION,

    last_post_at         TIMESTAMPTZ,
    growth_90d           DOUBLE PRECISION,

    adv_total            INTEGER NOT NULL DEFAULT 0,
    adv_repeat           INTEGER NOT NULL DEFAULT 0,
    adv_window_days      INTEGER,

    stats_scraped_at     TIMESTAMPTZ,
    built_at             TIMESTAMPTZ NOT NULL,

    UNIQUE (platform, username_lower)
);

CREATE TABLE "{schema}".channel_post (
    channel_id       BIGINT NOT NULL REFERENCES "{schema}".channel(id) ON DELETE CASCADE,
    platform_post_id TEXT NOT NULL,
    text             TEXT,
    url              TEXT,
    views            BIGINT,
    likes            INTEGER,
    reactions        INTEGER,
    comments         INTEGER,
    is_ad            BOOLEAN NOT NULL DEFAULT FALSE,
    posted_at        TIMESTAMPTZ,
    PRIMARY KEY (channel_id, platform_post_id)
);

CREATE INDEX ON "{schema}".channel_post (channel_id, posted_at DESC);

CREATE TABLE "{schema}".channel_history (
    channel_id  BIGINT NOT NULL REFERENCES "{schema}".channel(id) ON DELETE CASCADE,
    point_date  DATE NOT NULL,
    subscribers BIGINT,
    PRIMARY KEY (channel_id, point_date)
);

CREATE TABLE "{schema}".channel_category (
    channel_id    BIGINT NOT NULL REFERENCES "{schema}".channel(id) ON DELETE CASCADE,
    category_name TEXT NOT NULL,
    category_slug TEXT NOT NULL,
    PRIMARY KEY (channel_id, category_slug)
);

CREATE INDEX ON "{schema}".channel_category (category_slug);

CREATE TABLE "{schema}".channel_sibling (
    channel_id         BIGINT NOT NULL REFERENCES "{schema}".channel(id) ON DELETE CASCADE,
    sibling_channel_id BIGINT NOT NULL REFERENCES "{schema}".channel(id) ON DELETE CASCADE,
    PRIMARY KEY (channel_id, sibling_channel_id)
);

CREATE TABLE "{schema}".channel_advertiser (
    channel_id       BIGINT NOT NULL REFERENCES "{schema}".channel(id) ON DELETE CASCADE,
    label            TEXT NOT NULL,
    inn              TEXT,
    ogrn             TEXT,
    entity_type      TEXT,
    placements_count INTEGER NOT NULL DEFAULT 0,
    last_placed_at   TIMESTAMPTZ,
    rank             INTEGER NOT NULL,
    PRIMARY KEY (channel_id, rank)
);

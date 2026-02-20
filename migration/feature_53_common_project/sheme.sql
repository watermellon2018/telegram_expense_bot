-- Table: public.categories

-- DROP TABLE IF EXISTS public.categories;

CREATE TABLE IF NOT EXISTS public.categories
(
    category_id integer NOT NULL DEFAULT nextval('categories_category_id_seq'::regclass),
    user_id text COLLATE pg_catalog."default" NOT NULL,
    name character varying(255) COLLATE pg_catalog."default" NOT NULL,
    is_system boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    project_id integer,
    CONSTRAINT categories_pkey PRIMARY KEY (category_id),
    CONSTRAINT categories_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT fk_categories_project FOREIGN KEY (project_id)
        REFERENCES public.projects (project_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.categories
    OWNER to postgres;
-- Index: categories_project_name_idx

-- DROP INDEX IF EXISTS public.categories_project_name_idx;

CREATE UNIQUE INDEX IF NOT EXISTS categories_project_name_idx
    ON public.categories USING btree
    (project_id ASC NULLS LAST, lower(name::text) COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default
    WHERE is_active = true;
-- Index: idx_categories_user_id

-- DROP INDEX IF EXISTS public.idx_categories_user_id;

CREATE INDEX IF NOT EXISTS idx_categories_user_id
    ON public.categories USING btree
    (user_id COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;


-- Table: public.expenses

-- DROP TABLE IF EXISTS public.expenses;

CREATE TABLE IF NOT EXISTS public.expenses
(
    id integer NOT NULL DEFAULT nextval('expenses_id_seq'::regclass),
    user_id text COLLATE pg_catalog."default",
    date date,
    "time" time without time zone,
    amount numeric,
    category text COLLATE pg_catalog."default",
    description text COLLATE pg_catalog."default",
    month integer,
    category_id integer NOT NULL,
    project_id integer,
    CONSTRAINT expenses_pkey PRIMARY KEY (id),
    CONSTRAINT expenses_category_id_fkey FOREIGN KEY (category_id)
        REFERENCES public.categories (category_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE RESTRICT,
    CONSTRAINT fk_expenses_project FOREIGN KEY (project_id)
        REFERENCES public.projects (project_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.expenses
    OWNER to postgres;
-- Index: idx_expenses_category_id

-- DROP INDEX IF EXISTS public.idx_expenses_category_id;

CREATE INDEX IF NOT EXISTS idx_expenses_category_id
    ON public.expenses USING btree
    (category_id ASC NULLS LAST)
    TABLESPACE pg_default;

-- Table: public.project_invites

-- DROP TABLE IF EXISTS public.project_invites;

CREATE TABLE IF NOT EXISTS public.project_invites
(
    token text COLLATE pg_catalog."default" NOT NULL,
    project_id integer NOT NULL,
    inviter_id text COLLATE pg_catalog."default" NOT NULL,
    role character varying(20) COLLATE pg_catalog."default" DEFAULT 'editor'::character varying,
    created_at timestamp without time zone DEFAULT now(),
    expires_at timestamp without time zone NOT NULL,
    CONSTRAINT project_invites_pkey PRIMARY KEY (token),
    CONSTRAINT fk_invite_project FOREIGN KEY (project_id)
        REFERENCES public.projects (project_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT fk_invite_user FOREIGN KEY (inviter_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.project_invites
    OWNER to postgres;
-- Index: idx_invites_expires_at

-- DROP INDEX IF EXISTS public.idx_invites_expires_at;

CREATE INDEX IF NOT EXISTS idx_invites_expires_at
    ON public.project_invites USING btree
    (expires_at ASC NULLS LAST)
    TABLESPACE pg_default;

-- Table: public.project_members

-- DROP TABLE IF EXISTS public.project_members;

CREATE TABLE IF NOT EXISTS public.project_members
(
    project_id integer NOT NULL,
    user_id text COLLATE pg_catalog."default" NOT NULL,
    role character varying(20) COLLATE pg_catalog."default" NOT NULL,
    joined_at timestamp without time zone DEFAULT now(),
    CONSTRAINT project_members_pkey PRIMARY KEY (project_id, user_id),
    CONSTRAINT fk_project_id FOREIGN KEY (project_id)
        REFERENCES public.projects (project_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT fk_user FOREIGN KEY (user_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.project_members
    OWNER to postgres;

-- Table: public.projects

-- DROP TABLE IF EXISTS public.projects;

CREATE TABLE IF NOT EXISTS public.projects
(
    user_id text COLLATE pg_catalog."default" NOT NULL,
    project_name text COLLATE pg_catalog."default",
    created_date date,
    is_active boolean,
    project_id integer NOT NULL DEFAULT nextval('projects_global_project_id_seq'::regclass),
    CONSTRAINT projects_pkey PRIMARY KEY (project_id),
    CONSTRAINT projects_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES public.users (user_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.projects
    OWNER to postgres;

-- Table: public.users

-- DROP TABLE IF EXISTS public.users;

CREATE TABLE IF NOT EXISTS public.users
(
    user_id text COLLATE pg_catalog."default" NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    active_project_id integer,
    CONSTRAINT users_pkey PRIMARY KEY (user_id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.users
    OWNER to postgres;
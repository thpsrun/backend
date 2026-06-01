from django.db import migrations

RENAME_TABLES_SQL = """
-- Rename core user table
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'auth_user')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'accounts_customuser')
    THEN
        ALTER TABLE auth_user RENAME TO accounts_customuser;
    END IF;
END $$;

-- Rename M2M: groups
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'auth_user_groups')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'accounts_customuser_groups')
    THEN
        ALTER TABLE auth_user_groups RENAME TO accounts_customuser_groups;
    END IF;
END $$;

-- Rename M2M: user_permissions
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'auth_user_user_permissions')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'accounts_customuser_user_permissions')
    THEN
        ALTER TABLE auth_user_user_permissions RENAME TO accounts_customuser_user_permissions;
    END IF;
END $$;
"""

RENAME_M2M_COLUMNS_SQL = """
-- Rename user_id -> customuser_id in groups M2M
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser_groups' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE accounts_customuser_groups RENAME COLUMN user_id TO customuser_id;
    END IF;
END $$;

-- Rename user_id -> customuser_id in permissions M2M
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser_user_permissions' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE accounts_customuser_user_permissions
            RENAME COLUMN user_id TO customuser_id;
    END IF;
END $$;
"""

ADD_CUSTOM_COLUMNS_SQL = """
-- Add custom fields to accounts_customuser if they don't exist
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'encrypted_api_key'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN encrypted_api_key text NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'bio'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN bio text NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'therun_gg'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN therun_gg text NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'short_bio'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN short_bio varchar(100) NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'gradient_1'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN gradient_1 varchar(7) NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'gradient_2'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN gradient_2 varchar(7) NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'gradient_3'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN gradient_3 varchar(7) NULL;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'accounts_customuser' AND column_name = 'profile_bg'
    ) THEN
        ALTER TABLE accounts_customuser ADD COLUMN profile_bg varchar(100) NULL;
    END IF;
END $$;
"""

UPDATE_CONTENT_TYPE_SQL = """
-- Update django_content_type from auth.user to accounts.customuser
UPDATE django_content_type
SET app_label = 'accounts', model = 'customuser'
WHERE app_label = 'auth' AND model = 'user';
"""

RENAME_SEQUENCE_SQL = """
-- Rename the primary key sequence for consistency
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_sequences WHERE sequencename = 'auth_user_id_seq')
    THEN
        ALTER SEQUENCE auth_user_id_seq RENAME TO accounts_customuser_id_seq;
    END IF;
END $$;
"""

UPDATE_FK_REFERENCES_SQL = """
-- Update srl_players.user_id FK to point to accounts_customuser
-- (table rename handles the target, but constraint name is stale)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'srl_players_user_id_1ceae297_fk_auth_user_id'
        AND table_name = 'srl_players'
    ) THEN
        ALTER TABLE srl_players
            DROP CONSTRAINT srl_players_user_id_1ceae297_fk_auth_user_id;
        ALTER TABLE srl_players
            ADD CONSTRAINT srl_players_user_id_fk_accounts_customuser
            FOREIGN KEY (user_id) REFERENCES accounts_customuser(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

-- Update django_admin_log.user_id FK
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'django_admin_log_user_id_c564eba6_fk_auth_user_id'
        AND table_name = 'django_admin_log'
    ) THEN
        ALTER TABLE django_admin_log
            DROP CONSTRAINT django_admin_log_user_id_c564eba6_fk_auth_user_id;
        ALTER TABLE django_admin_log
            ADD CONSTRAINT django_admin_log_user_id_fk_accounts_customuser
            FOREIGN KEY (user_id) REFERENCES accounts_customuser(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(RENAME_TABLES_SQL, migrations.RunSQL.noop),
        migrations.RunSQL(RENAME_M2M_COLUMNS_SQL, migrations.RunSQL.noop),
        migrations.RunSQL(ADD_CUSTOM_COLUMNS_SQL, migrations.RunSQL.noop),
        migrations.RunSQL(UPDATE_CONTENT_TYPE_SQL, migrations.RunSQL.noop),
        migrations.RunSQL(RENAME_SEQUENCE_SQL, migrations.RunSQL.noop),
        migrations.RunSQL(UPDATE_FK_REFERENCES_SQL, migrations.RunSQL.noop),
    ]

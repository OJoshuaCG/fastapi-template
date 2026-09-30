-- Tabla de ejemplo usada por app/models/user_model.py.
-- Se aplica con el gestor de BD (ver database/README.md); los tests la crean solos.

CREATE TABLE IF NOT EXISTS users (
    id              INT          NOT NULL AUTO_INCREMENT,
    username        VARCHAR(50)  NOT NULL,
    email           VARCHAR(255) NOT NULL,
    -- Token Fernet (cifrado reversible, ver app/utils/passwords.py): ~270 chars para 128
    encrypted_password VARCHAR(512) NOT NULL,
    full_name       VARCHAR(100) NULL,
    notes           TEXT         NULL,
    is_active       TINYINT(1)   NOT NULL DEFAULT 1,
    is_superuser    TINYINT(1)   NOT NULL DEFAULT 0,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Fecha y hora de creación del registro',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Fecha y hora de última actualización del registro',
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tabla de usuarios del sistema';

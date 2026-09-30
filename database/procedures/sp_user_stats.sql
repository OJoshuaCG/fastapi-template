-- Ejemplo de stored procedure con varios result sets y SIGNAL (app/core/database.py:call_procedure).
--   await db.call_procedure("sp_user_stats", [only_active])
-- only_active: 1 = solo activos, 0 = todos. Otro valor → SIGNAL 45000 → HTTP 409 con el mensaje.

DROP PROCEDURE IF EXISTS sp_user_stats;

DELIMITER //
CREATE PROCEDURE sp_user_stats(IN only_active TINYINT)
BEGIN
    IF only_active NOT IN (0, 1) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El filtro only_active debe ser 0 o 1';
    END IF;

    -- Result set 1: totales
    SELECT COUNT(*) AS total, COALESCE(SUM(is_active), 0) AS active
    FROM users
    WHERE only_active = 0 OR is_active = 1;

    -- Result set 2: últimos 5 usuarios
    SELECT id, username
    FROM users
    WHERE only_active = 0 OR is_active = 1
    ORDER BY id DESC
    LIMIT 5;
END //
DELIMITER ;

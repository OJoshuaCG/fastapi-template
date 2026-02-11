from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.environments import DB_ENGINE, DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER
from app.exceptions.AppHttpException import AppHttpException
from app.utils import dict_utils


class Database:
    def __init__(
        self, 
        db_name: str=DB_NAME,
        db_user: str=DB_USER,
        db_pass: str=DB_PASS,
        db_host: str=DB_HOST,
        db_port: int=DB_PORT,
        db_engine: str=DB_ENGINE
    ):
        self.__db_name: str = db_name
        self.__db_user: str = db_user
        self.__db_pass: str = db_pass
        self.__db_host: str = db_host
        self.__db_port: str = db_port
        self.__db_engine: str = db_engine

        # DB_URL = f"mysql+pymysql://{self.__db_name}:{self.__db_pass}@{self.__db_host}:{self.__db_port}/{self.__db_name}"
        DB_URL = f"{self.__db_engine}://{self.__db_user}:{self.__db_pass}@{self.__db_host}:{self.__db_port}/{self.__db_name}"

        self.engine = create_engine(
            DB_URL,
            pool_size=10,
            max_overflow=20,
            pool_recycle=180,
            pool_pre_ping=True,
            connect_args={
                "charset": "utf8mb4",
                "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_general_ci",
            },
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

    @contextmanager
    def get_session(self):
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()
            self.SessionLocal.close_all()
            self.engine.dispose()

    def get_declarative_base_session(self):
        """
        Retorna sesión para uso con modelos ORM SQLAlchemy.

        Permite coexistencia de SQL directo (execute_query) y ORM.
        La sesión debe cerrarse manualmente después de su uso.

        Uso:
            from app.models import User
            session = db.get_declarative_base_session()
            try:
                user = session.query(User).filter(User.id == 1).first()
                session.commit()
            finally:
                session.close()

        Returns:
            Session: Sesión SQLAlchemy para operaciones ORM
        """
        return self.SessionLocal()

    def execute_query(
        self,
        query,
        params: dict = {},
        fetchone: bool | None = None,
        commit: bool | None = False,
    ):
        with self.get_session() as session:
            try:
                _query = text(query)
                result = session.execute(_query, params)
                # if commit:
                session.commit()  # Commit the transaction
                if fetchone:
                    row = result.fetchone()
                    return dict(row._mapping) if row else None
                elif fetchone is False:
                    return [dict(row._mapping) for row in result.fetchall()]

                if hasattr(result, "lastrowid") and result.lastrowid:
                    last_inserted_id = result.lastrowid
                    return last_inserted_id
                return result.rowcount
            except Exception as e:
                session.rollback()  # Rollback the transaction in case of an error
                session.close()
                context = {
                    "error_type": type(e).__name__,
                    "query": query,
                    "params": dict_utils._sanitize_dict(params),
                }

                if hasattr(e, "orig"):
                    context["message"] = str(e.orig)
                if hasattr(e, "statement"):
                    context["sql"] = e.statement
                if hasattr(e, "params"):
                    context["params"] = dict_utils._sanitize_dict(e.params)

                raise AppHttpException(
                    message="Ocurrio un error inesperado en el servidorB",
                    status_code=500,
                    context=context,
                )

    def call_procedure(self, procedure_name: str, params: list = []):
        try:
            with self.engine.begin() as conn:
                cursor = conn.connection.cursor()
                try:
                    cursor.callproc(procedure_name, params)
                    results = []

                    # Procesar el primer result set
                    if cursor.description:  # Si tiene columnas
                        rows = cursor.fetchall()
                        columns = [desc[0] for desc in cursor.description]
                        results.append(
                            [dict(zip(columns, row, strict=False)) for row in rows]
                        )

                    # Procesar result sets adicionales
                    while cursor.nextset():
                        if cursor.description:  # Si tiene columnas
                            rows = cursor.fetchall()
                            columns = [desc[0] for desc in cursor.description]
                            results.append(
                                [dict(zip(columns, row, strict=False)) for row in rows]
                            )

                    conn.commit()
                    cursor.close()

                    if not results:
                        results = False
                    elif len(results) == 1:
                        results = results[0]

                    return results
                finally:
                    cursor.close()
                    self.SessionLocal.close_all()
                    self.engine.dispose()

        except Exception as e:
            # conn.rollback()
            # conn.close()
            self.SessionLocal.close_all()
            self.engine.dispose()

            context = {
                "error_type": type(e).__name__,
            }
            context["error_code"] = str(e.args[0])
            context["message"] = str(e.args[1])

            if procedure_name:
                context["sp"] = procedure_name
            if params:
                context["params"] = dict_utils._sanitize_dict(params)

            if e.args[0] == 1644:  # Error customizado desde MariaDB, signal 45000
                raise AppHttpException(
                    f"Ocurrio un error inesperado en el servidor: {e.args[1]}",
                    status_code=500,
                    context=context,
                )

            raise AppHttpException(
                message="Ocurrio un error inesperado en el servidorB",
                status_code=500,
                context=context,
            )

        finally:
            conn.close()

    def get_host(self):
        return self.__db_host

    def get_port(self):
        return self.__db_port

    def get_name(self):
        return self.__db_name

    def get_user(self):
        return self.__db_user

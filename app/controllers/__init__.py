# Controllers - Lógica de Negocio (MVC)
#
# Los controllers contienen la lógica de negocio de la aplicación.
# Son llamados desde las routes y utilizan los models para interactuar con la BD.
#
# Patrón: Routes → Controllers → Models → Database
#
# Ejemplo:
#   from app.controllers.user_controller import UserController
#
#   controller = UserController()
#   user = controller.get_user(user_id=1)

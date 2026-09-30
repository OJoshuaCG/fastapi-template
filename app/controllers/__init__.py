"""
Controllers: lógica de negocio.

Reciben sus models por constructor y se inyectan en las routes con Depends:

    from app.controllers.user_controller import UserControllerDep

    @router.get("/{user_id}", response_model=ApiResponse[UserOut])
    async def get_user(user_id: int, users: UserControllerDep):
        return success(data=await users.get_user(user_id))

Patrón: Routes → Controllers → Models → Database
"""

class TaskPlanner:
    async def plan(self,intent):
        action=intent.get('action','unknown')
        return {'action':action,'steps':{'deploy':['inspect','detect','compare','confirm','update','commit'],'build':['dispatch','monitor','verify'],'fix':['logs','analyze','propose','approve','apply','rebuild']}.get(action,[])}

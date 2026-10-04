class NotificationService:
    async def safe_edit(self,message,text,**kwargs):
        try: await message.edit_text(text,**kwargs)
        except Exception: pass

from app import scheduler, messager

messager.auto_decline() # clean up expired hangs before scheduling new ones to get slots back
scheduler.create_hangs()
scheduler.schedule_hangs()
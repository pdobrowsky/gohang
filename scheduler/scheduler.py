# needs to connect to sqlalchemy, 
# get data down, 
# pull it into pandas
# clean up
# needs to process schedules to create possible hangs
# needs to write those results to new hangs table, update processed_at in schedule
# it runs every day (because you can update your schedule), but on Sundays it does the week ahead, rest of week it only does current week (for now)=
# ignore those already tried to schedule with since all on sms atm

# going to need to have eddit schedule eventually
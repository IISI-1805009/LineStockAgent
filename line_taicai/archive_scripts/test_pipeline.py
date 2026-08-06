import taicai_manager, database
print("Running single target test...")
taicai_manager.TARGETS_FILE = "targets.json" # Temporarily use empty or mock if needed
res = taicai_manager.run_update({"2330": 1000})
print("Update success!")

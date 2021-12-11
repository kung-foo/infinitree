import storage

storage.remount("/", readonly=False)

m = storage.getmount("/")
m.label = "INFINITREE"

storage.remount("/", readonly=True)

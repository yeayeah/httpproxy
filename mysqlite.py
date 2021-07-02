import time, random, sys
import sqlite3

class mysqlite:
	def _try_op(self, op, query, args=None, rmin=1.5, rmax=7.0):
		while 1:
			try:
				if query is None:
					return op()
				elif args is None:
					return op(query)
				else:
					return op(query, args)
			except sqlite3.OperationalError as e:
				if e.message == 'database is locked':
					print("zzZzzZZ: db is locked (%s)"%self.dbname)
					time.sleep(random.uniform(rmin, rmax))
					continue
				else:
					print('%s\nquery: %s\nargs: %s' % (str(sys.exc_info()), str(query), str(args)))
					raise e

	def execute(self, query, args = None, rmin=1.5, rmax=7.0):
		return self._try_op(self.cursor.execute, query, args, rmin, rmax)

	def executemany(self, query, args, rmin=1.5, rmax=7.0):
		while len(args):
			self._try_op(self.cursor.executemany, query, args[:500], rmin, rmax)
			args = args[500:]

	def commit(self, rmin=1.5, rmax=7.0):
		return self._try_op(self.handle.commit, None, None, rmin, rmax)

	def close(self):
		self.handle.close()

	def __init__(self, database, factory = None):
		self.handle = sqlite3.connect(database)
		if factory: self.handle.text_factory = factory
		self.cursor = self.handle.cursor()
		self.dbname = database

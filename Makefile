.PHONY: db run seed

db: ## Start Postgres, create DB, enable extensions
	@bash script/postgres_script.sh

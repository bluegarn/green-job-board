import os
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from supabase import create_client, Client # Import create_client and Client

# Set up logging for the database manager
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class SupabaseManager:
    """
    Manages connections and operations with the Supabase database using the official supabase-py client.
    """
    def __init__(self):
        # Load environment variables from a .env file.
        load_dotenv()

        # Fetch Supabase project URL and API key from environment variables.
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")

        # Initialize Supabase client
        self.supabase: Optional[Client] = None # Type hint for the Supabase client instance

        if not self.supabase_url or not self.supabase_key:
            logging.error("SUPABASE_URL or SUPABASE_KEY not found in .env. Please check your .env file.")
        else:
            try:
                # Create the Supabase client instance
                self.supabase = create_client(self.supabase_url, self.supabase_key)
                logging.info("Supabase client initialized successfully.")
            except Exception as e:
                logging.error(f"Failed to initialize Supabase client: {e}")
                self.supabase = None

    def connect(self) -> bool:
        """
        Checks if the Supabase client was successfully initialized.
        With supabase-py, explicit connection management (like psycopg2's connect()) isn't needed;
        the client manages API calls implicitly.
        Returns:
            bool: True if the Supabase client is ready, False otherwise.
        """
        return self.supabase is not None

    def close(self):
        """
        The supabase-py client doesn't require an explicit close method like psycopg2.
        This method is kept for compatibility with the scraper's call structure.
        """
        logging.info("Supabase client does not require explicit close.")
        pass # No action needed for supabase-py client

    def _insert_company_if_not_exists(self, company_name: str) -> bool:
        """
        Helper method to ensure a company exists in the 'public.companies' table.
        Uses 'upsert' which will insert if the 'name' (primary key) doesn't exist,
        or do nothing if it does (due to ON CONFLICT clause in table schema).
        Args:
            company_name (str): The name of the company to check/insert.
        Returns:
            bool: True if company exists or was successfully inserted/updated, False otherwise.
        """
        if not self.supabase:
            logging.error("Supabase client not initialized. Cannot handle company.")
            return False

        try:
            # Use upsert to insert the company if it doesn't exist.
            # 'on_conflict' ensures that if a company with the same 'name' already exists,
            # it won't throw an error; it will just do nothing (or update if you specified update fields).
            # Since 'name' is the primary key, a simple upsert with just 'name' is enough.
            response = self.supabase.table('companies').upsert(
                {'name': company_name, 'description': None, 'ESG_score': None}, # Set description and ESG_score to NULL
                on_conflict='name' # Conflict target is the 'name' column (your primary key)
            ).execute()

            # The 'upsert' method returns a response containing data.
            # If data is present, it means the operation (insert or no-op due to conflict) was successful.
            if response.data:
                logging.info(f"Company '{company_name}' ensured to exist in database.")
                return True
            else:
                logging.warning(f"Upsert operation for company '{company_name}' returned no data. Check for issues.")
                return False

        except Exception as e:
            logging.error(f"Error upserting company '{company_name}': {e}")
            return False

    def insert_jobs(self, jobs_data: List[Dict[str, Any]]) -> int:
        """
        Inserts a list of job dictionaries into the 'public.jobs' table.
        This method ensures the associated company exists before inserting the job.
        Args:
            jobs_data (List[Dict[str, Any]]): A list of dictionaries, each representing a job.
        Returns:
            int: The number of jobs successfully inserted.
        """
        if not self.supabase:
            logging.error("Supabase client not initialized. Cannot insert jobs.")
            return 0

        inserted_count = 0
        for job in jobs_data:
            try:
                business_name = job.get("company")
                title = job.get("title")
                description = job.get("description")
                location = job.get("location")
                link = job.get("link") # Get the link from the scraped data

                # Basic validation for required fields
                if not title or not description or not business_name:
                    logging.warning(f"Skipping job due to missing required data (title, description, or company). Job link: {job.get('link')}")
                    continue

                # Ensure the business_name exists in the 'companies' table before inserting the job.
                if business_name:
                    company_ok = self._insert_company_if_not_exists(business_name)
                    if not company_ok:
                        logging.error(f"Failed to ensure company '{business_name}' exists. Skipping job '{title}'.")
                        continue
                else:
                    logging.warning(f"Skipping job '{title}' due to missing business name.")
                    continue

                # Prepare data for insertion into the 'jobs' table.
                # 'expired_at', 'emission_estimate' are nullable and not provided, so they are omitted
                # or explicitly set to None if your table schema required a value.
                # 'status', 'impact_score', 'green_score' have defaults and are omitted.
                job_to_insert = {
                    "title": title,
                    "description": description,
                    "business_name": business_name,
                    "location": location,
                    "link": link,
                    # 'expired_at': None, # Optional: if you want to explicitly send None
                    # 'emission_estimate': None, # Optional: if you want to explicitly send None
                }

                # Insert the job into the 'jobs' table.
                response = self.supabase.table('jobs').insert(job_to_insert).execute()

                if response.data:
                    inserted_count += 1
                    logging.info(f"Successfully inserted job: '{title}' by '{business_name}'")
                else:
                    logging.warning(f"Insert operation for job '{title}' returned no data. Check for issues.")

            except Exception as e:
                logging.error(f"Error inserting job '{job.get('title')}': {e}")
        return inserted_count

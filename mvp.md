* **Core feature:** The chat interface allows the user to interact with the LLM to perform business tasks such as creating invoices and analyzing business data.

* **AI does not directly modify data.** The LLM creates an action template that is displayed to the user for confirmation or denial. Once confirmed, the action is executed through the business logic in the main application, not the AI infrastructure. The result is then returned to the conversation.

* **Traditional UI:** The application will also include the standard functionality expected from a Xero-style UI, such as a normal editable invoice list.

* **Invoice-first scope:** Start with invoices and expand into additional functionality once the invoice workflow is working well.

* **Example workflow:** The user asks, “Can you send an invoice to Bob’s Construction for $55?” The AI generates an invoice template and displays it in the chat for confirmation. The user confirms, the main application creates the invoice, and the AI responds that the invoice was successfully created for Bob’s Construction for $55.

* **Multi-step impactful actions:** Each impactful step requires its own confirmation. A single confirmation should not implicitly authorize multiple independent actions.

* **Business analytics:** The AI should be able to answer questions and perform analytics using business data, such as determining how much is currently unpaid, identifying overdue invoices, summarizing invoice totals, comparing revenue across periods, and answering other questions about the user's invoice data.

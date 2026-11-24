import { createAdminCaller } from './adminCaller'

export const customerEmailActions = createAdminCaller('customer_emails.')

export const EMAIL_TEMPLATE_FIELD = { options: 'Email Template' }
export const EMAIL_TEMPLATE_OPTIONS_PATH = 'customer_emails.get_email_template_options'

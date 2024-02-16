{
  'name': 'Credport by Grupo Quanam Colombia SAS',
  'version': '1.0',
  'description': 'Credport',
  'summary': '',
  'author': 'Grupo Quanam Colombia SAS',
  'website': 'https://grupoquanam.com.co',
  'license': 'LGPL-3',
  'category': 'credport, account, invoicing',
  'depends': [
    'account',
  ],
  'data': [
    # Security
    # 'security/ir.model.access.csv',
    # Views
    'views/credport_account_move_views.xml',
    # Reports
    'reports/custom_report.xml',
    'reports/external_layout.xml',
    'reports/paperformat.xml',
    'reports/reports.xml',
    'reports/journal_entries.xml',
    'reports/contingency_bill.xml',
    'reports/requisitions.xml',
  ],
  'demo': [
    ''
  ],
  'auto_install': False,
  'application': False,
  'assets': {
    
  }
}
-- Phase 4.4: Zarqa University Artificial Intelligence Plan 12 foundation.
-- Course records, dependency rules, and equivalencies are intentionally excluded.

insert into public.universities (
  id,
  name_ar,
  name_en,
  country,
  active
) values (
  '10000000-0000-0000-0000-000000000001',
  'جامعة الزرقاء',
  'Zarqa University',
  'Jordan',
  true
);

insert into public.faculties (
  id,
  university_id,
  name_ar,
  name_en,
  active
) values (
  '10000000-0000-0000-0000-000000000002',
  '10000000-0000-0000-0000-000000000001',
  'كلية تكنولوجيا المعلومات',
  'Faculty of Information Technology',
  true
);

insert into public.majors (
  id,
  faculty_id,
  name_ar,
  name_en,
  active
) values (
  '10000000-0000-0000-0000-000000000003',
  '10000000-0000-0000-0000-000000000002',
  'الذكاء الاصطناعي',
  'Artificial Intelligence',
  true
);

insert into public.academic_sources (
  id,
  university_id,
  source_type,
  source_url,
  title,
  plan_number,
  source_status
) values (
  '10000000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000001',
  'official_study_plan',
  'https://www.zu.edu.jo/ar/Collage/Science_and_Technology/Dept_Artificial/GetStudyPlan.aspx?Dept=1505&fac=15&id=110&page=205',
  'جامعة الزرقاء - قسم الذكاء الاصطناعي - الخطة الدراسية رقم (12)',
  '12',
  'unknown'
);

insert into public.study_plans (
  id,
  major_id,
  plan_number,
  total_credit_hours,
  status,
  source_id
) values (
  '10000000-0000-0000-0000-000000000005',
  '10000000-0000-0000-0000-000000000003',
  '12',
  132,
  'unknown',
  '10000000-0000-0000-0000-000000000004'
);

insert into public.requirement_groups (
  id,
  study_plan_id,
  group_code,
  name_ar,
  scope,
  requirement_type,
  required_credit_hours,
  display_order,
  active
) values
  (
    '10000000-0000-0000-0000-000000000011',
    '10000000-0000-0000-0000-000000000005',
    'UNIVERSITY_REQUIRED',
    'متطلبات الجامعة الإجبارية',
    'university',
    'required',
    18,
    1,
    true
  ),
  (
    '10000000-0000-0000-0000-000000000012',
    '10000000-0000-0000-0000-000000000005',
    'UNIVERSITY_ELECTIVE',
    'متطلبات الجامعة الاختيارية',
    'university',
    'elective',
    9,
    2,
    true
  ),
  (
    '10000000-0000-0000-0000-000000000013',
    '10000000-0000-0000-0000-000000000005',
    'FACULTY_REQUIRED',
    'متطلبات الكلية الإجبارية',
    'faculty',
    'required',
    21,
    3,
    true
  ),
  (
    '10000000-0000-0000-0000-000000000014',
    '10000000-0000-0000-0000-000000000005',
    'SUPPORTING_REQUIRED',
    'المتطلبات المساندة',
    'supporting',
    'required',
    12,
    4,
    true
  ),
  (
    '10000000-0000-0000-0000-000000000015',
    '10000000-0000-0000-0000-000000000005',
    'MAJOR_REQUIRED',
    'متطلبات التخصص الإجبارية',
    'major',
    'required',
    63,
    5,
    true
  ),
  (
    '10000000-0000-0000-0000-000000000016',
    '10000000-0000-0000-0000-000000000005',
    'MAJOR_ELECTIVE',
    'متطلبات التخصص الاختيارية',
    'major',
    'elective',
    9,
    6,
    true
  );

-- Phase 4.5A: selectable/listed courses for Zarqa University AI Plan 12.
-- Structured dependency rules and equivalencies are intentionally excluded.

begin;

create temporary table _ai_plan12_course_seed (
  course_code text primary key,
  name_ar text not null,
  credit_hours numeric(6, 2) not null,
  requirement_group_code text not null,
  raw_prerequisite_text text,
  prerequisite_logic_status text not null,
  learning_type text not null,
  delivery_mode text not null,
  display_order integer not null
) on commit drop;

insert into _ai_plan12_course_seed (
  course_code,
  name_ar,
  credit_hours,
  requirement_group_code,
  raw_prerequisite_text,
  prerequisite_logic_status,
  learning_type,
  delivery_mode,
  display_order
) values
  ('0200104', 'التربية الوطنية', 3, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 1),
  ('0200105', 'مهارات الاتصال والتواصل (اللغة العربية 1)', 3, 'UNIVERSITY_REQUIRED', '0200150,0201001', 'unresolved', 'نظري', 'الكتروني', 2),
  ('0200106', 'مهارات الاتصال والتواصل (اللغة الانجليزية 1)', 3, 'UNIVERSITY_REQUIRED', '0200151,0202001', 'unresolved', 'نظري', 'الكتروني', 3),
  ('0200110', 'العلوم العسكرية', 3, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 4),
  ('0200111', 'الثقافة الاسلامية وقضايا العصر', 3, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 5),
  ('0200115', 'تنمية المجتمع والعمل التطوعي', 0, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 6),
  ('0200153', 'المهارات الحياتية', 1, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 7),
  ('0200154', 'القيادة والمسؤولية المجتمعية', 1, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 8),
  ('0400202', 'الريادة والابتكار', 1, 'UNIVERSITY_REQUIRED', null, 'not_applicable', 'نظري', 'الكتروني', 9),
  ('0200113', 'تاريخ الاردن وفلسطين', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 10),
  ('0200114', 'القدس تاريخ وحضارة', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 11),
  ('0200122', 'مبادئ علم التربية', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 12),
  ('0200125', 'مبادئ علم القانون', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 13),
  ('0200127', 'اخلاقيات الطالب الجامعي', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 14),
  ('0200130', 'جرائم الارهاب', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 15),
  ('0200156', 'التنمية والبيئة', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 16),
  ('0300123', 'مبادئ علم الفلك', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 17),
  ('0300124', 'الثقافة العلمية', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 18),
  ('0300157', 'الثقافة الرقمية', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 19),
  ('0300161', 'الاسعافات الاولية', 3, 'UNIVERSITY_ELECTIVE', null, 'not_applicable', 'نظري', 'الكتروني', 20),
  ('0300153', 'اساسيات تكنولوجيا المعلومات', 3, 'FACULTY_REQUIRED', null, 'not_applicable', 'نظري', 'مدمج', 21),
  ('0300154', 'اساسيات الامن السيبراني', 3, 'FACULTY_REQUIRED', null, 'not_applicable', 'نظري', 'وجاهي', 22),
  ('0300155', 'تصميم المنطق الرقمي', 3, 'FACULTY_REQUIRED', null, 'not_applicable', 'نظري', 'وجاهي', 23),
  ('0300220', 'رياضيات متقطعة', 3, 'FACULTY_REQUIRED', '0300153', 'unresolved', 'نظري', 'مدمج', 24),
  ('1501110', 'برمجة الحاسوب (1)', 3, 'FACULTY_REQUIRED', '0300153', 'unresolved', 'نظري', 'وجاهي', 25),
  ('1501112', 'برمجة الحاسوب (2)', 3, 'FACULTY_REQUIRED', '1501110', 'unresolved', 'نظري', 'وجاهي', 26),
  ('1501221', 'تراكيب البيانات', 3, 'FACULTY_REQUIRED', '1501112', 'unresolved', 'نظري', 'وجاهي', 27),
  ('1509999', 'حلقة بحث لطلبة كلية تكنولوجيا المعلومات', 0, 'FACULTY_REQUIRED', null, 'not_applicable', 'نظري', 'وجاهي', 28),
  ('0200215', 'لغة انجليزية لأغراض خاصة بتكنولوجيا المعلومات (ESP-IT)', 3, 'SUPPORTING_REQUIRED', '0200106', 'unresolved', 'نظري', 'مدمج', 29),
  ('0300101', 'التفاضل والتكامل 1', 3, 'SUPPORTING_REQUIRED', null, 'not_applicable', 'نظري', 'وجاهي', 30),
  ('0300104', 'الاحصاء والاحتمالات لتكنولوجيا المعلومات', 3, 'SUPPORTING_REQUIRED', null, 'not_applicable', 'نظري', 'مدمج', 31),
  ('0301245', 'الجبر الخطي لتكنولوجيا المعلومات', 3, 'SUPPORTING_REQUIRED', null, 'not_applicable', 'نظري', 'وجاهي', 32),
  ('1501212', 'برمجة مرئية', 3, 'MAJOR_ELECTIVE', '1501222', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 33),
  ('1501360', 'مناهج واخلاقيات البحث العلمي', 3, 'MAJOR_ELECTIVE', null, 'not_applicable', 'التعلم القائم على المشاريع', 'مدمج', 34),
  ('1501385', 'برمجة الهواتف الذكية', 3, 'MAJOR_ELECTIVE', '1501112', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 35),
  ('1505211', 'لغات خاصة في البرمجة', 3, 'MAJOR_ELECTIVE', '1501112', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 36),
  ('1505303', 'المنطق الضبابي', 3, 'MAJOR_ELECTIVE', '0300220', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 37),
  ('1505351', 'علم الإدراك', 3, 'MAJOR_ELECTIVE', '1505201', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 38),
  ('1505365', 'استرجاع المعلومات', 3, 'MAJOR_ELECTIVE', '1501222', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 39),
  ('1505414', 'تعلم الالة التطبيقي', 3, 'MAJOR_ELECTIVE', '1505311', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 40),
  ('1505435', 'موضوعات خاصة في الذكاء الاصطناعي (1)', 3, 'MAJOR_ELECTIVE', null, 'not_applicable', 'التعلم القائم على المشاريع', 'مدمج', 41),
  ('1505436', 'موضوعات خاصة في الذكاء الاصطناعي (2)', 3, 'MAJOR_ELECTIVE', null, 'not_applicable', 'التعلم القائم على المشاريع', 'مدمج', 42),
  ('1505480', 'البيانات الضخمة', 3, 'MAJOR_ELECTIVE', '1501222', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 43),
  ('1505482', 'برمجة الروبوتات', 3, 'MAJOR_ELECTIVE', '1505381', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 44),
  ('1506493', 'إنترنت الأشياء', 3, 'MAJOR_ELECTIVE', '1501340', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 45),
  ('1501111', 'مختبر برمجة الحاسوب (1)', 1, 'MAJOR_REQUIRED', '0300153', 'unresolved', 'عملي', 'وجاهي', 46),
  ('1501113', 'مختبر برمجة الحاسوب (2)', 1, 'MAJOR_REQUIRED', '1501111', 'unresolved', 'عملي', 'وجاهي', 47),
  ('1501222', 'نظم قواعد البيانات', 3, 'MAJOR_REQUIRED', '1501112', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 48),
  ('1501321', 'تصميم وتحليل الخوارزميات', 3, 'MAJOR_REQUIRED', '1501221', 'unresolved', 'التعلم القائم على المشاريع', 'وجاهي', 49),
  ('1501340', 'شبكات الحاسوب', 3, 'MAJOR_REQUIRED', '1501112', 'unresolved', 'التعلم القائم على المشاريع', 'وجاهي', 50),
  ('1501430', 'نظم التشغيل', 3, 'MAJOR_REQUIRED', '1501221', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 51),
  ('1503270', 'مقدمة لهندسة البرمجيات', 3, 'MAJOR_REQUIRED', '0300153', 'unresolved', 'نظري', 'مدمج', 52),
  ('1505101', 'البرمجة بلغة بايثون', 3, 'MAJOR_REQUIRED', '1501110', 'unresolved', 'التعلم القائم على المشاريع', 'وجاهي', 53),
  ('1505201', 'مقدمة في الذكاء الاصطناعي', 3, 'MAJOR_REQUIRED', '0300153', 'unresolved', 'نظري', 'وجاهي', 54),
  ('1505223', 'برمجة وأدوات الذكاء الإصطناعي', 3, 'MAJOR_REQUIRED', '1505101', 'unresolved', 'التعلم القائم على المشاريع', 'وجاهي', 55),
  ('1505311', 'تعلم الالة', 3, 'MAJOR_REQUIRED', '1505101,1505201', 'unresolved', 'نظري', 'وجاهي', 56),
  ('1505320', 'تعلم الآلة المتقدم', 3, 'MAJOR_REQUIRED', '0300103,1505311', 'source_conflict', 'التعلم القائم على المشاريع', 'مدمج', 57),
  ('1505333', 'علم البيانات وتحليلها', 3, 'MAJOR_REQUIRED', '1501222', 'unresolved', 'نظري', 'وجاهي', 58),
  ('1505366', 'معالجة الصور الرقمية', 3, 'MAJOR_REQUIRED', '0301241,1505101', 'source_conflict', 'التعلم القائم على المشاريع', 'وجاهي', 59),
  ('1505367', 'تدريب ميداني في الذكاء الاصطناعي', 3, 'MAJOR_REQUIRED', null, 'not_applicable', 'عملي', 'مدمج', 60),
  ('1505381', 'مقدمة في الروبوتات', 3, 'MAJOR_REQUIRED', '1505201', 'unresolved', 'نظري', 'مدمج', 61),
  ('1505415', 'التعلم العميق التطبيقي', 3, 'MAJOR_REQUIRED', '1505311', 'unresolved', 'التعلم القائم على المشاريع', 'وجاهي', 62),
  ('1505441', 'معالجة اللغات الطبيعية', 3, 'MAJOR_REQUIRED', '1505311', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 63),
  ('1505461', 'الرؤية الحاسوبية', 3, 'MAJOR_REQUIRED', '1505366,1505415', 'unresolved', 'التعلم القائم على المشاريع', 'مدمج', 64),
  ('1505467', 'مشروع (1) في الذكاء الاصطناعي', 3, 'MAJOR_REQUIRED', null, 'not_applicable', 'عملي', 'مدمج', 65),
  ('1505468', 'مشروع (2) في الذكاء الاصطناعي', 3, 'MAJOR_REQUIRED', '1505467', 'unresolved', 'عملي', 'مدمج', 66),
  ('1506180', 'برمجة ويب (1)', 3, 'MAJOR_REQUIRED', '1501110', 'unresolved', 'نظري', 'وجاهي', 67),
  ('1506181', 'مختبر برمجة ويب (1)', 1, 'MAJOR_REQUIRED', '1501111', 'unresolved', 'عملي', 'وجاهي', 68);

insert into public.courses (
  university_id,
  course_code,
  name_ar,
  name_en,
  catalog_status,
  active
)
select
  '10000000-0000-0000-0000-000000000001',
  seed.course_code,
  seed.name_ar,
  null,
  'known',
  true
from _ai_plan12_course_seed seed;

insert into public.study_plan_courses (
  study_plan_id,
  course_id,
  requirement_group_id,
  credit_hours,
  learning_type,
  delivery_mode,
  raw_prerequisite_text,
  prerequisite_logic_status,
  verification_status,
  source_id,
  display_order,
  active
)
select
  '10000000-0000-0000-0000-000000000005',
  course.id,
  requirement_group.id,
  seed.credit_hours,
  seed.learning_type,
  seed.delivery_mode,
  seed.raw_prerequisite_text,
  seed.prerequisite_logic_status,
  'verified',
  '10000000-0000-0000-0000-000000000004',
  seed.display_order,
  true
from _ai_plan12_course_seed seed
join public.courses course
  on course.university_id = '10000000-0000-0000-0000-000000000001'
 and course.course_code = seed.course_code
join public.requirement_groups requirement_group
  on requirement_group.study_plan_id = '10000000-0000-0000-0000-000000000005'
 and requirement_group.group_code = seed.requirement_group_code;

commit;
